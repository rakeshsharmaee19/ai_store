"""Request logging middleware.

Logs request id, user id, method, path, status code and duration.
Never logs request bodies, headers, passwords, or secrets.
"""
import logging
import time
import uuid

logger = logging.getLogger("django")


class RequestLoggingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.request_id = str(uuid.uuid4())
        start = time.monotonic()
        response = self.get_response(request)
        duration_ms = round((time.monotonic() - start) * 1000, 2)

        user_id = getattr(getattr(request, "user", None), "id", None)
        logger.info(
            "request_id=%s method=%s path=%s status=%s user_id=%s duration_ms=%s",
            request.request_id,
            request.method,
            request.path,
            response.status_code,
            user_id,
            duration_ms,
        )
        response["X-Request-ID"] = request.request_id
        return response
