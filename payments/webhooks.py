"""
Stripe webhook handling. This view intentionally does NOT use JWT
authentication -- Stripe authenticates itself via a signature header, which
we verify against STRIPE_WEBHOOK_SECRET.
"""
import logging

from django.db import IntegrityError, transaction
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.authentication import BaseAuthentication
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import PaymentTransaction, StripeWebhookEvent
from .services import complete_payment, fail_payment
from .stripe_service import StripeService

logger = logging.getLogger("payments")


class NoAuthentication(BaseAuthentication):
    """Explicitly disables DRF's default JWT authentication for this view."""

    def authenticate(self, request):
        return None


class StripeWebhookView(APIView):
    authentication_classes = [NoAuthentication]
    permission_classes = [AllowAny]

    @csrf_exempt
    def post(self, request):
        payload = request.body
        sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

        try:
            event = StripeService().construct_webhook_event(payload=payload, sig_header=sig_header)
        except Exception:  # noqa: BLE001 - invalid signature/payload
            logger.warning("stripe_webhook_signature_invalid")
            return Response({"error": {"code": "INVALID_SIGNATURE", "message": "Invalid webhook signature."}}, status=status.HTTP_400_BAD_REQUEST)

        event_id = event["id"]
        event_type = event["type"]

        try:
            with transaction.atomic():
                webhook_event = StripeWebhookEvent.objects.create(
                    event_id=event_id, event_type=event_type, payload=event
                )
        except IntegrityError:
            # Duplicate delivery of an event we've already stored -- idempotent no-op.
            logger.info("stripe_webhook_duplicate event_id=%s", event_id)
            return Response(status=status.HTTP_200_OK)

        self._handle_event(event_type, event)

        webhook_event.processed = True
        from django.utils import timezone

        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["processed", "processed_at"])

        return Response(status=status.HTTP_200_OK)

    def _handle_event(self, event_type: str, event) -> None:
        data_object = event["data"]["object"]
        payment_intent_id = data_object.get("id")

        payment = PaymentTransaction.objects.filter(provider_transaction_id=payment_intent_id).first()
        if payment is None:
            logger.warning("stripe_webhook_no_matching_payment payment_intent_id=%s", payment_intent_id)
            return

        if event_type == "payment_intent.succeeded":
            complete_payment(payment=payment, provider_transaction_id=payment_intent_id)
        elif event_type == "payment_intent.payment_failed":
            reason = data_object.get("last_payment_error", {}).get("message", "Payment failed.")
            fail_payment(payment=payment, reason=reason)
        else:
            logger.info("stripe_webhook_unhandled_event_type type=%s", event_type)
