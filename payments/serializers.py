from rest_framework import serializers

from .models import PaymentTransaction, RefundRecord


class PaymentTransactionSerializer(serializers.ModelSerializer):
    order_number = serializers.CharField(source="order.order_number", read_only=True)

    class Meta:
        model = PaymentTransaction
        fields = [
            "id", "order", "order_number", "payment_method", "amount", "currency",
            "status", "provider", "provider_transaction_id", "failure_reason",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class CreateStripePaymentSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()


class CreateCryptoPaymentSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()


class VerifyCryptoPaymentSerializer(serializers.Serializer):
    payment_id = serializers.IntegerField()
    tx_hash = serializers.CharField(max_length=255)


class RefundRequestSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class RefundRecordSerializer(serializers.ModelSerializer):
    class Meta:
        model = RefundRecord
        fields = ["id", "payment", "amount", "provider_refund_id", "reason", "is_manual", "created_at"]
        read_only_fields = fields
