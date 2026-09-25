from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase

from agent.models import AgentConversation
from agent.services.agent_service import AgentService
from agent.services.llm_service import LLMResponse, ToolCallRequest
from orders.models import Order
from payments.models import PaymentTransaction
from products.models import Product

User = get_user_model()


def grant(user, *codenames):
    for codename in codenames:
        perm = Permission.objects.get(codename=codename, content_type__app_label="agent")
        user.user_permissions.add(perm)


class AgentLoopTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(email="agentstaff@example.com", password="StrongPassword123!", is_staff=True)
        self.product = Product.objects.create(name="Widget", price=Decimal("15.00"), stock_quantity=10)
        self.order = Order.objects.create(user=self.staff, order_number="ORD-1001", total_amount=Decimal("15.00"))

    def test_simple_final_response_no_tools(self):
        with patch("agent.services.llm_service.LLMService.get_completion") as mock_completion:
            mock_completion.return_value = LLMResponse(content="Hello! How can I help?", tool_calls=[])
            result = AgentService().handle_message(user=self.staff, conversation=None, message="Hi")
        self.assertEqual(result["message"], "Hello! How can I help?")
        self.assertEqual(result["iterations"], 1)

    def test_single_tool_call(self):
        grant(self.staff, "can_read_order")
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_1", name="get_order", arguments={"order_number": "ORD-1001"})]),
            LLMResponse(content="Order ORD-1001 is PENDING_PAYMENT.", tool_calls=[]),
        ]
        with patch("agent.services.llm_service.LLMService.get_completion", side_effect=responses):
            result = AgentService().handle_message(user=self.staff, conversation=None, message="Status of ORD-1001?")
        self.assertIn("PENDING_PAYMENT", result["message"])

    def test_multiple_tool_calls(self):
        grant(self.staff, "can_read_order", "can_read_payment")
        PaymentTransaction.objects.create(
            order=self.order, user=self.staff, payment_method="STRIPE", amount=Decimal("15.00"),
            status="FAILED", idempotency_key="k1",
        )
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_1", name="get_order", arguments={"order_number": "ORD-1001"})]),
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_2", name="get_order_payments", arguments={"order_number": "ORD-1001"})]),
            LLMResponse(content="Payment failed.", tool_calls=[]),
        ]
        with patch("agent.services.llm_service.LLMService.get_completion", side_effect=responses):
            result = AgentService().handle_message(user=self.staff, conversation=None, message="Why did ORD-1001 fail?")
        self.assertEqual(result["iterations"], 3)

    def test_unknown_tool(self):
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_1", name="nonexistent_tool", arguments={})]),
            LLMResponse(content="I couldn't do that.", tool_calls=[]),
        ]
        with patch("agent.services.llm_service.LLMService.get_completion", side_effect=responses):
            result = AgentService().handle_message(user=self.staff, conversation=None, message="Do something weird")
        self.assertEqual(result["message"], "I couldn't do that.")

    def test_invalid_tool_arguments(self):
        grant(self.staff, "can_read_order")
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_1", name="get_order", arguments={})]),
            LLMResponse(content="I need an order number.", tool_calls=[]),
        ]
        with patch("agent.services.llm_service.LLMService.get_completion", side_effect=responses):
            result = AgentService().handle_message(user=self.staff, conversation=None, message="check order")
        self.assertEqual(result["message"], "I need an order number.")

    def test_tool_failure(self):
        grant(self.staff, "can_read_order")
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_1", name="get_order", arguments={"order_number": "ORD-DOESNOTEXIST"})]),
            LLMResponse(content="I couldn't find that order.", tool_calls=[]),
        ]
        with patch("agent.services.llm_service.LLMService.get_completion", side_effect=responses):
            result = AgentService().handle_message(user=self.staff, conversation=None, message="check bad order")
        self.assertEqual(result["message"], "I couldn't find that order.")

    def test_permission_denied(self):
        # staff has NO agent permissions granted
        responses = [
            LLMResponse(content=None, tool_calls=[ToolCallRequest(id="call_1", name="get_order", arguments={"order_number": "ORD-1001"})]),
            LLMResponse(content="I don't have permission to do that.", tool_calls=[]),
        ]
        with patch("agent.services.llm_service.LLMService.get_completion", side_effect=responses):
            result = AgentService().handle_message(user=self.staff, conversation=None, message="check order")
        self.assertEqual(result["message"], "I don't have permission to do that.")

    def test_maximum_iterations_reached(self):
        from django.test import override_settings

        grant(self.staff, "can_read_order")
        infinite_response = LLMResponse(
            content=None, tool_calls=[ToolCallRequest(id="call_x", name="get_order", arguments={"order_number": "ORD-1001"})]
        )
        with override_settings(AGENT_MAX_ITERATIONS=3):
            with patch("agent.services.llm_service.LLMService.get_completion", return_value=infinite_response):
                result = AgentService().handle_message(user=self.staff, conversation=None, message="loop forever")
        self.assertEqual(result["iterations"], 3)
        self.assertIn("maximum number of tool iterations", result["message"])
