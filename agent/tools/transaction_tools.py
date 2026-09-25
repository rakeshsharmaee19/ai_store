"""Read-only tools exposing payment transaction data to the agent."""
from common.exceptions import ToolExecutionError
from payments.models import PaymentTransaction

from .registry import ToolDefinition, registry


def _serialize_payment(payment: PaymentTransaction) -> dict:
    return {
        "id": payment.id,
        "order_number": payment.order.order_number,
        "user_id": payment.user_id,
        "payment_method": payment.payment_method,
        "amount": str(payment.amount),
        "currency": payment.currency,
        "status": payment.status,
        "provider": payment.provider,
        "provider_transaction_id": payment.provider_transaction_id,
        "failure_reason": payment.failure_reason,
        "created_at": payment.created_at.isoformat(),
    }


def get_payment(*, payment_id: int) -> dict:
    payment = PaymentTransaction.objects.select_related("order").filter(id=payment_id).first()
    if payment is None:
        raise ToolExecutionError(f"No payment found with id={payment_id}.")
    return _serialize_payment(payment)


def get_order_payments(*, order_number: str) -> dict:
    payments = PaymentTransaction.objects.select_related("order").filter(order__order_number=order_number)
    if not payments.exists():
        raise ToolExecutionError(f"No payments found for order_number='{order_number}'.")
    return {"payments": [_serialize_payment(p) for p in payments]}


def get_failed_payments(*, user_id: int, limit: int = 10) -> dict:
    payments = (
        PaymentTransaction.objects.select_related("order")
        .filter(user_id=user_id, status="FAILED")
        .order_by("-created_at")[: min(limit, 50)]
    )
    return {"payments": [_serialize_payment(p) for p in payments]}


registry.register(
    ToolDefinition(
        name="get_payment",
        description="Get details of a single payment transaction by its numeric id.",
        parameters={
            "type": "object",
            "properties": {"payment_id": {"type": "integer"}},
            "required": ["payment_id"],
        },
        handler=get_payment,
        required_permission="agent.can_read_payment",
        read_only=True,
        requires_confirmation=False,
    )
)

registry.register(
    ToolDefinition(
        name="get_order_payments",
        description="List all payment transactions associated with an order_number.",
        parameters={
            "type": "object",
            "properties": {"order_number": {"type": "string"}},
            "required": ["order_number"],
        },
        handler=get_order_payments,
        required_permission="agent.can_read_payment",
        read_only=True,
        requires_confirmation=False,
    )
)

registry.register(
    ToolDefinition(
        name="get_failed_payments",
        description="List recent FAILED payment transactions for a given user id.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 10},
            },
            "required": ["user_id"],
        },
        handler=get_failed_payments,
        required_permission="agent.can_read_payment",
        read_only=True,
        requires_confirmation=False,
    )
)
