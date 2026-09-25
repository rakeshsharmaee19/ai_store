from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.urls import reverse
from rest_framework.test import APITestCase

from agent.models import AgentActionApproval, AgentConversation
from orders.models import Order
from payments.models import PaymentTransaction
from products.models import Product

User = get_user_model()


class ApprovalTests(APITestCase):
    def setUp(self):
        self.finance_staff = User.objects.create_user(email="finance@example.com", password="StrongPassword123!", is_staff=True)
        perm = Permission.objects.get(codename="can_refund_payment", content_type__app_label="agent")
        self.finance_staff.user_permissions.add(perm)

        self.customer = User.objects.create_user(email="cust2@example.com", password="StrongPassword123!")
        self.product = Product.objects.create(name="RefundableItem", price=Decimal("30.00"), stock_quantity=5)
        self.order = Order.objects.create(user=self.customer, order_number="ORD-REFUND1", total_amount=Decimal("30.00"), status="PAID")
        self.payment = PaymentTransaction.objects.create(
            order=self.order, user=self.customer, payment_method="STRIPE", amount=Decimal("30.00"),
            status="COMPLETED", provider="stripe", provider_transaction_id="pi_refund1", idempotency_key="k-refund1",
        )
        self.conversation = AgentConversation.objects.create(user=self.finance_staff, title="refund chat")
        self.approval = AgentActionApproval.objects.create(
            conversation=self.conversation, action="refund_payment",
            arguments={"payment_id": self.payment.id, "order_number": "ORD-REFUND1", "reason": "customer request"},
            requested_by=self.finance_staff,
        )

    @patch("payments.stripe_service.StripeService.create_refund", return_value="re_123")
    def test_approve_executes_refund(self, mock_refund):
        self.client.force_authenticate(user=self.finance_staff)
        response = self.client.post(reverse("agent-approval-approve", args=[self.approval.id]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "EXECUTED")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.status, "REFUNDED")

    def test_reject_approval(self):
        self.client.force_authenticate(user=self.finance_staff)
        response = self.client.post(reverse("agent-approval-reject", args=[self.approval.id]), {"note": "not eligible"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "REJECTED")

    @patch("payments.stripe_service.StripeService.create_refund", return_value="re_dup")
    def test_duplicate_approval_execution_is_idempotent(self, mock_refund):
        self.client.force_authenticate(user=self.finance_staff)
        first = self.client.post(reverse("agent-approval-approve", args=[self.approval.id]))
        second = self.client.post(reverse("agent-approval-approve", args=[self.approval.id]))
        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        mock_refund.assert_called_once()  # Stripe refund only called once despite two approve calls

    def test_unauthorized_user_cannot_approve(self):
        self.client.force_authenticate(user=self.customer)
        response = self.client.post(reverse("agent-approval-approve", args=[self.approval.id]))
        self.assertEqual(response.status_code, 403)
