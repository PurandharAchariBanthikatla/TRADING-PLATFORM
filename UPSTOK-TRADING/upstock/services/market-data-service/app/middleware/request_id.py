import uuid

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Stamps every request/response with a correlation id and binds it into
    structlog's contextvars so every log line emitted while handling this
    request carries it automatically -- this is what lets you grep one
    request's full story out of aggregated logs, and is the anchor OTel
    trace ids get attached to once tracing is wired in.
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        request_id = request.headers.get("x-request-id", str(uuid.uuid4()))
        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(request_id=request_id)

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response
