"""
Write/action tools. These are the tools that actually change state.

Sensitive actions (refunds) NEVER execute directly from the LLM's tool call.
Instead they create an AgentActionApproval row and return a
"pending approval" result. Only a human hitting the approval endpoints can
actually execute the underlying PaymentService/OrderService call.

`cancel_order` and `send_customer_email` are lower-risk and execute
immediately, but still go through Django's permission system and the normal
domain services -- never a direct DB/ORM shortcut invented just for the agent.
"""
from common.exceptions import ToolExecutionError, UnauthorizedAction
from orders.models import Order
from orders.services import cancel_order as cancel_order_service
from payments.models import PaymentTransaction

from .registry import ToolDefinition, registry


def request_refund(*, order_number: str, reason: str = "", conversation_id: int | None = None, requested_by_id: int | None = None) -> dict:
    """
    Creates a pending AgentActionApproval for a refund. This function NEVER
    calls PaymentService.refund_payment() itself -- execution only happens
    after POST /api/agent/approvals/{id}/approve/ by a human.
    """
    from .. import models as agent_models  # local import to avoid circulars

    order = Order.objects.filter(order_number=order_number).first()
    if order is None:
        raise ToolExecutionError(f"No order found with order_number='{order_number}'.")

    payment = PaymentTransaction.objects.filter(order=order, status="COMPLETED").order_by("-created_at").first()
    if payment is None:
        raise ToolExecutionError(f"No completed payment found for order '{order_number}' to refund.")

    approval = agent_models.AgentActionApproval.objects.create(
        conversation_id=conversation_id,
        action="refund_payment",
        arguments={"payment_id": payment.id, "order_number": order_number, "reason": reason},
        requested_by_id=requested_by_id,
    )
    return {
        "status": "approval_required",
        "approval_id": approval.id,
        "action": "refund",
        "message": "The refund request has been created and is awaiting human approval. It has NOT been executed.",
    }


def cancel_order(*, order_number: str) -> dict:
    order = Order.objects.filter(order_number=order_number).first()
    if order is None:
        raise ToolExecutionError(f"No order found with order_number='{order_number}'.")
    try:
        order = cancel_order_service(order=order)
    except Exception as exc:  # noqa: BLE001
        raise ToolExecutionError(str(exc)) from exc
    return {"order_number": order.order_number, "status": order.status, "message": "Order cancelled successfully."}


def send_customer_email(*, user_id: int, subject: str, body: str) -> dict:
    """
    In this learning project this enqueues a Celery task rather than sending
    real email, so the flow is demonstrable without an SMTP provider.
    """
    from django.contrib.auth import get_user_model

    from agent.tasks import send_customer_email_task

    User = get_user_model()
    if not User.objects.filter(id=user_id).exists():
        raise ToolExecutionError(f"No user found with id={user_id}.")

    send_customer_email_task.delay(user_id=user_id, subject=subject, body=body)
    return {"status": "queued", "user_id": user_id, "subject": subject}


registry.register(
    ToolDefinition(
        name="request_refund",
        description=(
            "Request a refund for the completed payment on an order. This does NOT execute the refund -- "
            "it creates a pending approval that a human staff member must explicitly approve."
        ),
        parameters={
            "type": "object",
            "properties": {
                "order_number": {"type": "string"},
                "reason": {"type": "string", "description": "Why the refund is being requested."},
            },
            "required": ["order_number"],
        },
        handler=request_refund,
        required_permission="agent.can_refund_payment",
        read_only=False,
        requires_confirmation=True,
        needs_context=True,
    )
)

registry.register(
    ToolDefinition(
        name="cancel_order",
        description="Cancel an order that is still in a cancellable state (PENDING_PAYMENT or PAYMENT_PROCESSING).",
        parameters={
            "type": "object",
            "properties": {"order_number": {"type": "string"}},
            "required": ["order_number"],
        },
        handler=cancel_order,
        required_permission="agent.can_cancel_order",
        read_only=False,
        requires_confirmation=False,
    )
)

registry.register(
    ToolDefinition(
        name="send_customer_email",
        description="Send (queue) a support email to a customer by user id.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
            "required": ["user_id", "subject", "body"],
        },
        handler=send_customer_email,
        required_permission="agent.can_email_customer",
        read_only=False,
        requires_confirmation=False,
    )
)
