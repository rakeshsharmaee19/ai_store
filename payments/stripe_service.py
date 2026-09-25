"""
Thin wrapper around the Stripe SDK. This is the ONLY module in the project
allowed to import `stripe`. Views and the agent layer never touch Stripe
directly -- they go through PaymentService -> StripeService.
"""
import logging

import stripe
from django.conf import settings

logger = logging.getLogger("payments")


class StripeService:
    def __init__(self):
        stripe.api_key = settings.STRIPE_SECRET_KEY

    def create_payment_intent(self, *, amount, currency: str, order_id: int, idempotency_key: str) -> stripe.PaymentIntent:
        """
        Amount must already be validated server-side (never trust the
        frontend). Stripe expects the smallest currency unit (e.g. cents).
        """
        amount_in_minor_units = int(amount * 100)
        return stripe.PaymentIntent.create(
            amount=amount_in_minor_units,
            currency=currency.lower(),
            metadata={"order_id": str(order_id)},
            idempotency_key=idempotency_key,
        )

    def create_refund(self, *, payment_intent_id: str, idempotency_key: str) -> str:
        if not payment_intent_id:
            raise ValueError("Cannot refund a payment with no provider_transaction_id.")
        refund = stripe.Refund.create(
            payment_intent=payment_intent_id,
            idempotency_key=idempotency_key,
        )
        return refund.id

    def construct_webhook_event(self, *, payload: bytes, sig_header: str) -> stripe.Event:
        return stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
