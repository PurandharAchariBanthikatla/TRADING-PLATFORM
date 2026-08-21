"""Event distribution for market data.

**Why Redis Streams instead of Kafka/Redpanda:** the target architecture
for this phase calls for Kafka/Redpanda. Standing up and operating a real
broker is real infrastructure work independent of application code, and
isn't something this service should silently substitute without saying so.
Redis Streams is used here as the concrete backing implementation because
it actually provides the properties this phase requires and tests --
ordered per-stream logs, consumer groups, per-consumer delivery tracking,
explicit ack, and reclaim-on-timeout for retry/dead-lettering (XADD,
XREADGROUP, XACK, XPENDING, XCLAIM) -- not a pub/sub stand-in that fakes
those properties. The public interface below (`publish`, `consume_group`,
`ack`, `claim_stale_and_deadletter`) is intentionally broker-agnostic:
swapping to Kafka/Redpanda later is a rewrite of this one module, not a
change to any caller (simulator, candle aggregator, ticker service, or the
API layer).

**Event envelope versioning:** every event is wrapped in the schemas in
app/schemas/events.py, which carry an explicit `event_version`. Consumers
should reject/dead-letter an event whose version they don't understand
rather than guess at its shape -- see CandleAggregator's handling.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import redis.asyncio as redis

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


def dlq_stream_name(stream: str) -> str:
    return f"{stream}.dlq"


@dataclass(frozen=True)
class StreamMessage:
    id: str
    fields: dict[str, Any]
    delivery_count: int


class EventBus:
    def __init__(self, client: redis.Redis | None = None):
        self._owns_client = client is None
        self._client = client or redis.from_url(settings.REDIS_URL, decode_responses=True)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def publish(self, stream: str, event: dict) -> str:
        """Appends one event (already a JSON-serializable dict, typically
        `SomeEvent.model_dump(mode="json")`) to `stream`. The stream is
        capped approximately (`XADD ... MAXLEN ~`) so it doesn't grow
        unbounded -- approximate trimming is intentionally cheap (doesn't
        require an exact scan) and is fine for a distribution log whose
        durable copy of history lives in Postgres, not in the stream itself.
        """
        message_id = await self._client.xadd(
            stream,
            {"payload": json.dumps(event, default=str)},
            maxlen=settings.EVENT_STREAM_MAXLEN_APPROX,
            approximate=True,
        )
        return message_id

    async def ensure_group(self, stream: str, group: str) -> None:
        try:
            await self._client.xgroup_create(stream, group, id="0", mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume_group(
        self, stream: str, group: str, consumer: str, *, count: int = 10, block_ms: int = 1000
    ) -> list[StreamMessage]:
        """Reads new (never-before-delivered-to-this-group) messages. Does
        NOT read this consumer's own pending (unacked) messages -- that's
        what claim_stale_and_deadletter is for, keeping "get new work" and
        "recover stuck work" as separate, individually testable operations.
        """
        result = await self._client.xreadgroup(group, consumer, {stream: ">"}, count=count, block=block_ms)
        if not result:
            return []
        _, entries = result[0]
        return [
            StreamMessage(id=entry_id, fields=json.loads(fields["payload"]), delivery_count=1)
            for entry_id, fields in entries
        ]

    async def ack(self, stream: str, group: str, message_id: str) -> None:
        await self._client.xack(stream, group, message_id)

    async def claim_stale_and_deadletter(
        self,
        stream: str,
        group: str,
        consumer: str,
        *,
        min_idle_ms: int | None = None,
        max_delivery_attempts: int | None = None,
    ) -> tuple[list[StreamMessage], int]:
        """Reclaims messages that have been pending (delivered but never
        acked) for longer than `min_idle_ms` -- e.g. a consumer crashed
        mid-processing. Messages that have now been delivered
        `max_delivery_attempts` times or more are moved to `{stream}.dlq`
        and acked off the original stream rather than reclaimed again, so
        one poison event can't loop forever.

        Returns (messages reclaimed for retry, count moved to DLQ).
        """
        min_idle_ms = min_idle_ms if min_idle_ms is not None else settings.EVENT_STREAM_CLAIM_MIN_IDLE_MS
        max_delivery_attempts = (
            max_delivery_attempts
            if max_delivery_attempts is not None
            else settings.EVENT_STREAM_MAX_DELIVERY_ATTEMPTS
        )

        pending = await self._client.xpending_range(stream, group, min="-", max="+", count=100)
        if not pending:
            return [], 0

        retryable_ids: list[str] = []
        deadletter_ids: list[str] = []
        for entry in pending:
            entry_id = entry["message_id"]
            delivery_count = entry["times_delivered"]
            idle_ms = entry["time_since_delivered"]
            if idle_ms < min_idle_ms:
                continue
            if delivery_count >= max_delivery_attempts:
                deadletter_ids.append(entry_id)
            else:
                retryable_ids.append(entry_id)

        deadlettered = 0
        if deadletter_ids:
            # redis-py's xclaim stub wants a homogeneous-typed tuple/list
            # literal, not tuple[str, ...]; the runtime call is correct
            # (xclaim accepts any sequence of message ids) -- this is a
            # stub limitation, not a real type mismatch.
            claimed = await self._client.xclaim(
                stream,
                group,
                consumer,
                min_idle_ms,
                tuple(deadletter_ids),  # type: ignore[arg-type]
            )
            for entry_id, fields in claimed:
                event = json.loads(fields["payload"])
                await self._client.xadd(
                    dlq_stream_name(stream),
                    {"payload": json.dumps({"original_id": entry_id, "event": event}, default=str)},
                )
                await self._client.xack(stream, group, entry_id)
                deadlettered += 1
                log.error("event_deadlettered", stream=stream, group=group, original_id=entry_id)

        reclaimed: list[StreamMessage] = []
        if retryable_ids:
            claimed = await self._client.xclaim(
                stream,
                group,
                consumer,
                min_idle_ms,
                tuple(retryable_ids),  # type: ignore[arg-type]
            )
            for entry_id, fields in claimed:
                reclaimed.append(
                    StreamMessage(id=entry_id, fields=json.loads(fields["payload"]), delivery_count=2)
                )

        return reclaimed, deadlettered
