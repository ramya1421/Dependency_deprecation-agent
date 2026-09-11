import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from dda.api.routes.health import router as health_router
from dda.api.routes.kb import router as kb_router
from dda.api.routes.scans import router as scans_router

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="Dependency Deprecation Agent",
        description=(
            "Scans repos for deprecated/vulnerable/EOL dependencies and "
            "generates cited migration plans."
        ),
        version="0.1.0",
    )

    app.include_router(scans_router)
    app.include_router(kb_router)
    app.include_router(health_router)

    @app.middleware("http")
    async def correlation_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        # Reuse the scan_id from the path when available so API and background
        # task logs share the same correlation ID.
        correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
        request.state.correlation_id = correlation_id
        response = await call_next(request)
        response.headers["X-Correlation-ID"] = correlation_id
        logger.info(
            "http_request",
            extra={
                "correlation_id": correlation_id,
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )
        return response

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled_error", extra={"path": request.url.path})
        return JSONResponse(status_code=500, content={"detail": "Internal server error"})

    return app


# Entry point referenced in Makefile: uvicorn dda.api.app:app
app = create_app()
