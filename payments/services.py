"""
Core payment orchestration: state machine transitions, order-linkage,
refunds and audit logging. This is the ONLY layer allowed to mutate
PaymentTransaction/Order status. Views and the agent's tool handlers call
into this service -- they never touch the state machine directly.
"""
from django.db import transaction

from common.constants import (
    PAYMENT_COMPLETED,
    PAYMENT_METHOD_CRYPTO,
    PAYMENT_METHOD_STRIPE,
    PAYMENT_REFUNDED,
    PAYMENT_TRANSITIONS,
)
from common.exceptions import (
    InvalidPaymentTransition,
    PaymentAlreadyCompleted,
    UnauthorizedAction,
)
from common.utils import generate_idempotency_key
from orders.services import mark_order_failed, mark_order_paid

from .models import AuditLog, PaymentTransaction, RefundRecord


def write_audit_log(*, actor, action: str, resource_type: str, resource_id, metadata: dict | None = None, ip_address: str | None = None) -> AuditLog:
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        resource_type=resource_type,
        resource_id=str(resource_id),
        metadata=metadata or {},
        ip_address=ip_address,
    )


def transition_payment_status(*, payment: PaymentTransaction, new_status: str) -> PaymentTransaction:
    """Enforce the payment state machine. Raises InvalidPaymentTransition on illegal moves."""
    allowed = PAYMENT_TRANSITIONS.get(payment.status, set())
    if new_status not in allowed:
        raise InvalidPaymentTransition(
            f"Cannot transition payment from '{payment.status}' to '{new_status}'."
        )
    payment.status = new_status
    payment.save(update_fields=["status", "updated_at"])
    return payment


@transaction.atomic
def create_payment_transaction(*, order, user, payment_method: str, amount, currency: str, provider: str = "", metadata: dict | None = None) -> PaymentTransaction:
    return PaymentTransaction.objects.create(
        order=order,
        user=user,
        payment_method=payment_method,
        amount=amount,
        currency=currency,
        provider=provider,
        idempotency_key=generate_idempotency_key(),
        metadata=metadata or {},
    )


@transaction.atomic
def complete_payment(*, payment: PaymentTransaction, provider_transaction_id: str = "") -> PaymentTransaction:
    """
    Marks a payment COMPLETED and the linked order PAID. Idempotent: if the
    payment is already completed, this is a safe no-op (protects against
    duplicate Stripe webhook retries or duplicate crypto verification calls).
    """
    payment = PaymentTransaction.objects.select_for_update().get(id=payment.id)
    if payment.status == PAYMENT_COMPLETED:
        return payment  # already processed -- idempotent no-op

    if payment.status == "PROCESSING":
        transition_payment_status(payment=payment, new_status=PAYMENT_COMPLETED)
    else:
        # Some providers (crypto) may go straight from INITIATED to COMPLETED
        # once verified; allow that explicit path too.
        payment.status = PAYMENT_COMPLETED
        payment.save(update_fields=["status", "updated_at"])

    if provider_transaction_id:
        payment.provider_transaction_id = provider_transaction_id
        payment.save(update_fields=["provider_transaction_id", "updated_at"])

    mark_order_paid(order=payment.order)
    return payment


@transaction.atomic
def fail_payment(*, payment: PaymentTransaction, reason: str) -> PaymentTransaction:
    payment = PaymentTransaction.objects.select_for_update().get(id=payment.id)
    if payment.status == PAYMENT_COMPLETED:
        # Never downgrade a completed payment because of a late/duplicate failure event.
        return payment
    payment.status = "FAILED"
    payment.failure_reason = reason
    payment.save(update_fields=["status", "failure_reason", "updated_at"])
    mark_order_failed(order=payment.order)
    return payment


@transaction.atomic
def refund_payment(*, payment: PaymentTransaction, actor, reason: str = "", idempotency_key: str | None = None) -> RefundRecord:
    """
    Refunds MUST go through this service so the state machine, audit log and
    provider-specific behaviour stay consistent. Stripe refunds are executed
    automatically via the provider API; crypto refunds are always manual.
    """
    payment = PaymentTransaction.objects.select_for_update().get(id=payment.id)

    if payment.status != PAYMENT_COMPLETED:
        raise PaymentAlreadyCompleted("Only completed payments can be refunded.")

    idempotency_key = idempotency_key or generate_idempotency_key()
    existing = RefundRecord.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing  # idempotent replay

    provider_refund_id = ""
    is_manual = payment.payment_method == PAYMENT_METHOD_CRYPTO

    if payment.payment_method == PAYMENT_METHOD_STRIPE:
        from .stripe_service import StripeService

        provider_refund_id = StripeService().create_refund(
            payment_intent_id=payment.provider_transaction_id,
            idempotency_key=idempotency_key,
        )
    elif payment.payment_method == PAYMENT_METHOD_CRYPTO:
        # Crypto has no automated refund path -- this creates a manual
        # workflow record for an operator to action off-chain.
        provider_refund_id = ""

    transition_payment_status(payment=payment, new_status=PAYMENT_REFUNDED)

    from common.constants import ORDER_REFUNDED

    payment.order.status = ORDER_REFUNDED
    payment.order.save(update_fields=["status", "updated_at"])

    refund = RefundRecord.objects.create(
        payment=payment,
        initiated_by=actor,
        amount=payment.amount,
        provider_refund_id=provider_refund_id,
        idempotency_key=idempotency_key,
        reason=reason,
        is_manual=is_manual,
    )

    write_audit_log(
        actor=actor,
        action="REFUND",
        resource_type="PaymentTransaction",
        resource_id=payment.id,
        metadata={"order": payment.order.order_number, "amount": str(payment.amount), "manual": is_manual},
    )
    return refund


def verify_order_ownership(*, order, user) -> None:
    if order.user_id != user.id and not user.is_staff:
        raise UnauthorizedAction("You do not own this order.")
