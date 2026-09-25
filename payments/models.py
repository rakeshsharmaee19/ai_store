from django.conf import settings
from django.db import models

from common.constants import (
    PAYMENT_INITIATED,
    PAYMENT_METHOD_CHOICES,
    PAYMENT_STATUS_CHOICES,
)


class PaymentTransaction(models.Model):
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="payments")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments")

    payment_method = models.CharField(max_length=16, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=16, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_INITIATED)

    provider = models.CharField(max_length=32, blank=True)  # e.g. "stripe", "ethereum"
    provider_transaction_id = models.CharField(max_length=255, blank=True, db_index=True)
    idempotency_key = models.CharField(max_length=64, unique=True)

    failure_reason = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["user", "status"]),
            models.Index(fields=["order"]),
        ]

    def __str__(self) -> str:
        return f"{self.payment_method} payment for {self.order.order_number} ({self.status})"


class StripeWebhookEvent(models.Model):
    """Tracks processed Stripe webhook events for idempotency."""

    event_id = models.CharField(max_length=255, unique=True, db_index=True)
    event_type = models.CharField(max_length=100)
    payload = models.JSONField()
    processed = models.BooleanField(default=False)

    created_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.event_type} ({self.event_id})"


class RefundRecord(models.Model):
    """Audit-friendly record of a refund, separate from the payment's own status."""

    payment = models.ForeignKey(PaymentTransaction, on_delete=models.PROTECT, related_name="refunds")
    initiated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    provider_refund_id = models.CharField(max_length=255, blank=True)
    idempotency_key = models.CharField(max_length=64, unique=True)
    reason = models.TextField(blank=True)
    is_manual = models.BooleanField(default=False)  # True for crypto (no automated refund)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Refund of {self.amount} for payment #{self.payment_id}"


class AuditLog(models.Model):
    """
    Immutable-by-convention audit trail for sensitive actions.
    Never written to or controlled by the LLM directly -- only Django
    services write audit entries, after their own authorization checks pass.
    """

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="audit_entries")
    action = models.CharField(max_length=100)
    resource_type = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=100)
    metadata = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["action"]), models.Index(fields=["resource_type", "resource_id"])]

    def __str__(self) -> str:
        return f"{self.action} on {self.resource_type}#{self.resource_id}"
