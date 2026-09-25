"""Custom application exceptions and a consistent DRF error response format."""
import logging

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

logger = logging.getLogger("django")


class ApplicationError(Exception):
    """Base class for all domain-level application errors."""

    code = "APPLICATION_ERROR"
    message = "An application error occurred."
    http_status = status.HTTP_400_BAD_REQUEST

    def __init__(self, message: str | None = None, code: str | None = None, http_status: int | None = None):
        self.message = message or self.message
        self.code = code or self.code
        self.http_status = http_status or self.http_status
        super().__init__(self.message)


class InvalidOrderState(ApplicationError):
    code = "INVALID_ORDER_STATE"
    message = "This order cannot transition to the requested state."


class PaymentAlreadyCompleted(ApplicationError):
    code = "PAYMENT_ALREADY_COMPLETED"
    message = "This payment has already been completed."


class InsufficientStock(ApplicationError):
    code = "INSUFFICIENT_STOCK"
    message = "Insufficient stock for the requested quantity."


class UnauthorizedAction(ApplicationError):
    code = "UNAUTHORIZED_ACTION"
    message = "You are not authorized to perform this action."
    http_status = status.HTTP_403_FORBIDDEN


class ToolNotFound(ApplicationError):
    code = "TOOL_NOT_FOUND"
    message = "The requested agent tool does not exist."
    http_status = status.HTTP_404_NOT_FOUND


class ToolExecutionError(ApplicationError):
    code = "TOOL_EXECUTION_ERROR"
    message = "The agent tool failed to execute."
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR


class InvalidCryptoTransaction(ApplicationError):
    code = "INVALID_CRYPTO_TRANSACTION"
    message = "The provided crypto transaction could not be verified."


class InvalidPaymentTransition(ApplicationError):
    code = "INVALID_PAYMENT_TRANSITION"
    message = "This payment status transition is not allowed."


class ApprovalRequired(ApplicationError):
    code = "APPROVAL_REQUIRED"
    message = "This action requires human approval before it can be executed."
    http_status = status.HTTP_202_ACCEPTED


class RateLimitExceeded(ApplicationError):
    code = "RATE_LIMIT_EXCEEDED"
    message = "Too many requests. Please slow down."
    http_status = status.HTTP_429_TOO_MANY_REQUESTS


def custom_exception_handler(exc, context):
    """
    Ensures every error response (both DRF's own exceptions and our
    ApplicationError family) follows the same envelope:

        {"error": {"code": "...", "message": "..."}}

    Never leaks stack traces to the client.
    """
    if isinstance(exc, ApplicationError):
        logger.warning("application_error code=%s message=%s", exc.code, exc.message)
        return Response({"error": {"code": exc.code, "message": exc.message}}, status=exc.http_status)

    response = drf_exception_handler(exc, context)
    if response is not None:
        detail = response.data
        # Normalize DRF's default error shapes into our envelope.
        if isinstance(detail, dict) and "error" not in detail:
            message = detail.get("detail", detail)
            response.data = {
                "error": {
                    "code": "REQUEST_ERROR",
                    "message": str(message) if not isinstance(message, (dict, list)) else message,
                }
            }
        return response

    # Unhandled exception: never leak internals.
    logger.exception("unhandled_exception")
    return Response(
        {"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred."}},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
