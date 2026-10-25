import time
import uuid

import structlog

logger = structlog.get_logger()

# statuses at or above this are logged as warnings rather than info
CLIENT_ERROR_THRESHOLD = 400


class ASGILoggingMiddleware:
    """ Custom ASGI access logging middleware. """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        

        client = scope.get("client")
        structlog.contextvars.clear_contextvars()

        with structlog.contextvars.bound_contextvars(
            path=scope.get("path"),
            method=scope.get("method"),
            client_ip=client[0] if client else None,
        ):
            response_status = None

            async def send_with_status(message):
                nonlocal response_status
                if message["type"] == "http.response.start":
                    response_status = message["status"]
                await send(message)

            start_time = time.perf_counter()
            try:
                await self.app(scope, receive, send_with_status)
            except Exception:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                logger.error(
                    "Request failed with unhandled exception",
                    duration_ms=duration_ms,
                    exc_info=True,
                )
                raise
            else:
                duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
                log = logger.info
                if response_status is not None and response_status >= CLIENT_ERROR_THRESHOLD:
                    log = logger.warning
                log(
                    "Request processed",
                    status_code=response_status,
                    duration_ms=duration_ms,
                )
