from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.routes import health, ledger
from app.core.config import settings
from app.core.logging import configure_logging, get_logger
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware

configure_logging()
log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("service_starting", environment=settings.ENVIRONMENT, service=settings.SERVICE_NAME)
    yield
    log.info("service_stopping", service=settings.SERVICE_NAME)


app = FastAPI(
    title="Exchange Ledger Service",
    description="Immutable double-entry accounting core: ledger accounts, "
    "balanced transactions, balances, and reconciliation. Internal service "
    "-- not exposed directly to end users, only via api-gateway routing "
    "(added when the gateway proxies to it) or called service-to-service.",
    version="0.1.0",
    docs_url="/docs" if settings.ENVIRONMENT != "production" else None,
    redoc_url="/redoc" if settings.ENVIRONMENT != "production" else None,
    lifespan=lifespan,
)

# No CORSMiddleware here on purpose: this service is never called directly
# from a browser, only from other backend services / api-gateway, so there
# is no browser-origin allowlist to maintain.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestIDMiddleware)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = jsonable_encoder(exc.errors(), custom_encoder={Exception: str})
    log.warning("validation_error", path=request.url.path, errors=errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": "Validation failed.", "errors": errors},
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail}, headers=exc.headers)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    log.error("unhandled_exception", path=request.url.path, error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, content={"detail": "Internal server error."}
    )


app.include_router(health.router)
app.include_router(ledger.router, prefix=settings.API_V1_PREFIX)
