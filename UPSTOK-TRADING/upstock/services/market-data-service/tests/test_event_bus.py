import asyncio

import pytest


@pytest.mark.asyncio
async def test_publish_and_consume_roundtrip(event_bus):
    stream = "test.stream.1"
    group = "test-group"
    await event_bus.ensure_group(stream, group)

    await event_bus.publish(stream, {"hello": "world", "n": 1})

    messages = await event_bus.consume_group(stream, group, "consumer-1", count=10, block_ms=100)
    assert len(messages) == 1
    assert messages[0].fields == {"hello": "world", "n": 1}


@pytest.mark.asyncio
async def test_unacked_message_is_not_redelivered_to_a_new_read(event_bus):
    """Once XREADGROUP has delivered a message to a consumer, a plain
    consume_group call for '>' (new messages) must not hand it out again
    -- it's pending, not gone; recovering it is claim_stale_and_deadletter's
    job, not consume_group's.
    """
    stream = "test.stream.2"
    group = "test-group"
    await event_bus.ensure_group(stream, group)
    await event_bus.publish(stream, {"x": 1})

    first = await event_bus.consume_group(stream, group, "consumer-1", count=10, block_ms=100)
    assert len(first) == 1

    second = await event_bus.consume_group(stream, group, "consumer-1", count=10, block_ms=100)
    assert second == []


@pytest.mark.asyncio
async def test_ack_removes_message_from_pending(event_bus):
    stream = "test.stream.3"
    group = "test-group"
    await event_bus.ensure_group(stream, group)
    await event_bus.publish(stream, {"x": 1})

    [message] = await event_bus.consume_group(stream, group, "consumer-1", count=10, block_ms=100)
    await event_bus.ack(stream, group, message.id)

    reclaimed, deadlettered = await event_bus.claim_stale_and_deadletter(
        stream, group, "sweeper", min_idle_ms=0, max_delivery_attempts=5
    )
    assert reclaimed == []
    assert deadlettered == 0


@pytest.mark.asyncio
async def test_stale_unacked_message_is_reclaimed_for_retry(event_bus):
    stream = "test.stream.4"
    group = "test-group"
    await event_bus.ensure_group(stream, group)
    await event_bus.publish(stream, {"x": 1})

    await event_bus.consume_group(stream, group, "consumer-1", count=10, block_ms=100)
    # Never acked -- simulate consumer-1 crashing mid-processing.
    await asyncio.sleep(0.05)

    reclaimed, deadlettered = await event_bus.claim_stale_and_deadletter(
        stream, group, "consumer-2", min_idle_ms=10, max_delivery_attempts=5
    )
    assert len(reclaimed) == 1
    assert deadlettered == 0


@pytest.mark.asyncio
async def test_message_exceeding_max_delivery_attempts_is_deadlettered(event_bus, redis_client):
    stream = "test.stream.5"
    group = "test-group"
    await event_bus.ensure_group(stream, group)
    await event_bus.publish(stream, {"poison": True})

    # Deliver once, then repeatedly reclaim-without-acking to run the
    # delivery count up to just under the threshold, exactly as a handler
    # that keeps throwing would. max_delivery_attempts=3: delivery starts
    # at 1 (initial read); each claim call below checks the *current*
    # count and, if still under threshold, reclaims (which itself bumps
    # the count by one for next time) -- so it takes two such calls to
    # reach delivery=3, and the third call is the one that sees >= 3 and
    # dead-letters instead of reclaiming again.
    await event_bus.consume_group(stream, group, "consumer-1", count=10, block_ms=100)
    for _ in range(2):
        await asyncio.sleep(0.02)
        await event_bus.claim_stale_and_deadletter(
            stream, group, "consumer-1", min_idle_ms=10, max_delivery_attempts=3
        )

    await asyncio.sleep(0.02)
    reclaimed, deadlettered = await event_bus.claim_stale_and_deadletter(
        stream, group, "consumer-1", min_idle_ms=10, max_delivery_attempts=3
    )
    assert deadlettered == 1

    dlq_len = await redis_client.xlen(f"{stream}.dlq")
    assert dlq_len == 1
