"""Cross-cutting HTTP middleware for context, logging, timing, and headers."""

import logging
from time import perf_counter
from uuid import uuid4

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.constants.core import (
    HEADER_CONTENT_TYPE_OPTIONS,
    HEADER_CORRELATION_ID,
    HEADER_FRAME_OPTIONS,
    HEADER_PERMISSIONS_POLICY,
    HEADER_PROCESS_TIME,
    HEADER_REFERRER_POLICY,
    HEADER_REQUEST_ID,
)
from app.core.context import RequestContext, reset_request_context, set_request_context
from app.core.utils.dates import utc_now

logger = logging.getLogger(__name__)


class CoreRequestMiddleware(BaseHTTPMiddleware):
    """Apply the common HTTP concerns required by every API endpoint."""

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        """Initialize context, log the request lifecycle, and set safe headers."""
        request_id = request.headers.get(HEADER_REQUEST_ID, str(uuid4()))
        correlation_id = request.headers.get(HEADER_CORRELATION_ID, str(request_id))
        client_ip = request.client.host if request.client is not None else None
        context = RequestContext(
            request_id=request_id,
            correlation_id=correlation_id,
            client_ip=client_ip,
            requested_at=utc_now(),
        )
        request.state.context = context
        context_token = set_request_context(context)
        started_at = perf_counter()
        logger.info(
            "Request received method=%s path=%s correlation_id=%s client_ip=%s",
            request.method,
            request.url.path,
            context.correlation_id,
            context.client_ip,
        )
        try:
            response = await call_next(request)
            elapsed_ms = (perf_counter() - started_at) * 1000
            self._set_response_headers(
                response, context.correlation_id, request_id, elapsed_ms
            )
            logger.info(
                "Request completed method=%s path=%s status_code=%s duration_ms=%.2f "
                "correlation_id=%s",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
                context.correlation_id,
            )
            return response
        finally:
            reset_request_context(context_token)

    @staticmethod
    def _set_response_headers(
        response: Response,
        correlation_id: str,
        request_id: str,
        elapsed_ms: float,
    ) -> None:
        """Attach traceability, timing, and baseline security headers."""
        response.headers[HEADER_CORRELATION_ID] = correlation_id
        response.headers[HEADER_REQUEST_ID] = request_id
        response.headers[HEADER_PROCESS_TIME] = f"{elapsed_ms:.2f}"
        response.headers[HEADER_CONTENT_TYPE_OPTIONS] = "nosniff"
        response.headers[HEADER_FRAME_OPTIONS] = "DENY"
        response.headers[HEADER_REFERRER_POLICY] = "no-referrer"
        response.headers[HEADER_PERMISSIONS_POLICY] = (
            "camera=(), microphone=(), geolocation=()"
        )
