from django.contrib import admin

from .models import AuditLog, PaymentTransaction, RefundRecord, StripeWebhookEvent


@admin.register(PaymentTransaction)
class PaymentTransactionAdmin(admin.ModelAdmin):
    list_display = ["id", "order", "user", "payment_method", "amount", "status", "created_at"]
    list_filter = ["payment_method", "status"]
    search_fields = ["order__order_number", "user__email", "provider_transaction_id"]


@admin.register(StripeWebhookEvent)
class StripeWebhookEventAdmin(admin.ModelAdmin):
    list_display = ["event_id", "event_type", "processed", "created_at"]
    list_filter = ["event_type", "processed"]


@admin.register(RefundRecord)
class RefundRecordAdmin(admin.ModelAdmin):
    list_display = ["id", "payment", "amount", "is_manual", "created_at"]


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ["action", "resource_type", "resource_id", "actor", "created_at"]
    list_filter = ["action", "resource_type"]
    search_fields = ["resource_id", "actor__email"]
