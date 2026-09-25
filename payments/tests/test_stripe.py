from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase

from orders.models import Order
from payments.models import PaymentTransaction, StripeWebhookEvent
from products.models import Product

User = get_user_model()


class StripePaymentTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="StrongPassword123!")
        self.product = Product.objects.create(name="Item", price=Decimal("10.00"), stock_quantity=10)
        self.order = Order.objects.create(user=self.user, order_number="ORD-TEST1", total_amount=Decimal("10.00"))
        self.client.force_authenticate(user=self.user)

    @patch("payments.views.StripeService.create_payment_intent")
    def test_create_payment_intent(self, mock_create):
        mock_create.return_value = MagicMock(id="pi_123", client_secret="secret_abc")
        response = self.client.post(reverse("stripe-create"), {"order_id": self.order.id}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["client_secret"], "secret_abc")
        self.assertTrue(PaymentTransaction.objects.filter(order=self.order, provider_transaction_id="pi_123").exists())


class StripeWebhookTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer2@example.com", password="StrongPassword123!")
        self.product = Product.objects.create(name="Item2", price=Decimal("20.00"), stock_quantity=10)
        self.order = Order.objects.create(user=self.user, order_number="ORD-TEST2", total_amount=Decimal("20.00"))
        self.payment = PaymentTransaction.objects.create(
            order=self.order, user=self.user, payment_method="STRIPE", amount=Decimal("20.00"),
            status="PROCESSING", provider="stripe", provider_transaction_id="pi_456",
            idempotency_key="key-webhook-1",
        )

    def _fake_event(self, event_type, event_id="evt_1"):
        return {
            "id": event_id,
            "type": event_type,
            "data": {"object": {"id": "pi_456", "last_payment_error": {"message": "card_declined"}}},
        }

    @patch("payments.webhooks.StripeService.construct_webhook_event")
    def test_webhook_success_marks_order_paid(self, mock_construct):
        mock_construct.return_value = self._fake_event("payment_intent.succeeded")
        response = self.client.post(
            reverse("stripe-webhook"), data=b"{}", content_type="application/json",
            HTTP_STRIPE_SIGNATURE="fake-sig",
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(self.payment.status, "COMPLETED")
        self.assertEqual(self.order.status, "PAID")

    @patch("payments.webhooks.StripeService.construct_webhook_event")
    def test_webhook_failure_marks_order_failed(self, mock_construct):
        mock_construct.return_value = self._fake_event("payment_intent.payment_failed")
        response = self.client.post(
            reverse("stripe-webhook"), data=b"{}", content_type="application/json",
            HTTP_STRIPE_SIGNATURE="fake-sig",
        )
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "FAILED")

    @patch("payments.webhooks.StripeService.construct_webhook_event")
    def test_duplicate_webhook_is_idempotent(self, mock_construct):
        mock_construct.return_value = self._fake_event("payment_intent.succeeded", event_id="evt_dup")
        self.client.post(reverse("stripe-webhook"), data=b"{}", content_type="application/json", HTTP_STRIPE_SIGNATURE="fake-sig")
        self.client.post(reverse("stripe-webhook"), data=b"{}", content_type="application/json", HTTP_STRIPE_SIGNATURE="fake-sig")
        self.assertEqual(StripeWebhookEvent.objects.filter(event_id="evt_dup").count(), 1)

    @patch("payments.webhooks.StripeService.construct_webhook_event", side_effect=Exception("bad sig"))
    def test_invalid_signature_rejected(self, mock_construct):
        response = self.client.post(reverse("stripe-webhook"), data=b"{}", content_type="application/json", HTTP_STRIPE_SIGNATURE="bad")
        self.assertEqual(response.status_code, 400)
