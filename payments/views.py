from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.exceptions import UnauthorizedAction
from common.utils import get_client_ip
from orders.models import Order

from .crypto_service import CryptoPaymentService
from .models import PaymentTransaction
from .serializers import (
    CreateCryptoPaymentSerializer,
    CreateStripePaymentSerializer,
    PaymentTransactionSerializer,
    RefundRecordSerializer,
    RefundRequestSerializer,
    VerifyCryptoPaymentSerializer,
)
from .services import (
    complete_payment,
    create_payment_transaction,
    refund_payment,
    verify_order_ownership,
)
from .stripe_service import StripeService


class CreateStripePaymentView(APIView):
    """POST /api/payments/stripe/create/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateStripePaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = Order.objects.get(id=serializer.validated_data["order_id"])
        verify_order_ownership(order=order, user=request.user)

        payment = create_payment_transaction(
            order=order,
            user=request.user,
            payment_method="STRIPE",
            amount=order.total_amount,  # NEVER trust a client-supplied amount
            currency=order.currency,
            provider="stripe",
        )

        intent = StripeService().create_payment_intent(
            amount=order.total_amount,
            currency=order.currency,
            order_id=order.id,
            idempotency_key=payment.idempotency_key,
        )
        payment.provider_transaction_id = intent.id
        payment.status = "PROCESSING"
        payment.save(update_fields=["provider_transaction_id", "status", "updated_at"])

        return Response(
            {
                "payment": PaymentTransactionSerializer(payment).data,
                "client_secret": intent.client_secret,
            },
            status=status.HTTP_201_CREATED,
        )


class CreateCryptoPaymentView(APIView):
    """POST /api/payments/crypto/create/"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = CreateCryptoPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = Order.objects.get(id=serializer.validated_data["order_id"])
        verify_order_ownership(order=order, user=request.user)

        payment = create_payment_transaction(
            order=order,
            user=request.user,
            payment_method="CRYPTO",
            amount=order.total_amount,
            currency=order.currency,
            provider="web3",
        )

        from django.conf import settings

        return Response(
            {
                "payment": PaymentTransactionSerializer(payment).data,
                "receiving_address": settings.CRYPTO_RECEIVING_ADDRESS,
                "chain_id": settings.CRYPTO_CHAIN_ID,
                "amount": str(order.total_amount),
                "order_id": order.id,
            },
            status=status.HTTP_201_CREATED,
        )


class VerifyCryptoPaymentView(APIView):
    """
    POST /api/payments/crypto/verify/

    The backend independently verifies the transaction on-chain via Web3 --
    it never trusts the client's claim that the payment succeeded.
    """

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = VerifyCryptoPaymentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = PaymentTransaction.objects.select_related("order").get(
            id=serializer.validated_data["payment_id"]
        )
        if payment.user_id != request.user.id and not request.user.is_staff:
            raise UnauthorizedAction("You do not own this payment.")

        if payment.status == "COMPLETED":
            # Idempotent: already verified previously.
            return Response(PaymentTransactionSerializer(payment).data)

        expected_wei = CryptoPaymentService.amount_to_wei(payment.amount)
        tx = CryptoPaymentService().verify_transaction(
            tx_hash=serializer.validated_data["tx_hash"], expected_amount_wei=expected_wei
        )

        payment = complete_payment(payment=payment, provider_transaction_id=tx.tx_hash)
        return Response(PaymentTransactionSerializer(payment).data)


class PaymentHistoryView(APIView):
    """GET /api/payments/ - authenticated user's own payment history (staff sees all)."""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        qs = PaymentTransaction.objects.select_related("order")
        if not request.user.is_staff:
            qs = qs.filter(user=request.user)
        return Response(PaymentTransactionSerializer(qs, many=True).data)


class RefundPaymentView(APIView):
    """POST /api/payments/{id}/refund/ - staff-only, with idempotency + audit."""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, pk):
        if not request.user.has_perm("agent.payment.refund") and not request.user.is_staff:
            raise UnauthorizedAction("You do not have permission to issue refunds.")

        serializer = RefundRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        print(request.data)

        payment = PaymentTransaction.objects.get(id=pk)
        refund = refund_payment(
            payment=payment,
            actor=request.user,
            reason=serializer.validated_data.get("reason", ""),
        )
        return Response(RefundRecordSerializer(refund).data, status=status.HTTP_201_CREATED)
