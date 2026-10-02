from django.conf import settings
from django.db import models

from common.constants import (
    AGENT_ROLE_CHOICES,
    AGENT_TOOL_CALL_STATUS_CHOICES,
    APPROVAL_PENDING,
    APPROVAL_STATUS_CHOICES,
    CONVERSATION_OPEN,
    CONVERSATION_STATUS_CHOICES,
)


class AgentConversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="agent_conversations")
    title = models.CharField(max_length=255, blank=True)
    status = models.CharField(max_length=16, choices=CONVERSATION_STATUS_CHOICES, default=CONVERSATION_OPEN)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Conversation #{self.id}"


class AgentMessage(models.Model):
    conversation = models.ForeignKey(AgentConversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=16, choices=AGENT_ROLE_CHOICES)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"[{self.role}] {self.content[:50]}"


class AgentToolCall(models.Model):
    conversation = models.ForeignKey(AgentConversation, on_delete=models.CASCADE, related_name="tool_calls")
    tool_name = models.CharField(max_length=100)
    arguments = models.JSONField(default=dict)
    result = models.JSONField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=AGENT_TOOL_CALL_STATUS_CHOICES)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def __str__(self) -> str:
        return f"{self.tool_name} ({self.status})"


class AgentActionApproval(models.Model):
    """
    Human-in-the-loop gate for sensitive write actions (e.g. refunds).
    The LLM can only ever CREATE a pending approval -- it can never approve
    or execute one. Only a staff user calling the approval endpoints can.
    """

    conversation = models.ForeignKey(AgentConversation, on_delete=models.CASCADE, related_name="approvals")
    action = models.CharField(max_length=100)
    arguments = models.JSONField(default=dict)

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="requested_approvals"
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="approved_approvals"
    )
    status = models.CharField(max_length=16, choices=APPROVAL_STATUS_CHOICES, default=APPROVAL_PENDING)

    result = models.JSONField(null=True, blank=True)
    error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    approved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} ({self.status})"


class AgentPermissionMarker(models.Model):
    """
    This model has no meaningful data -- it exists purely to hang Django's
    permission framework on, so we get real, auditable, admin-manageable
    permissions like "agent.can_read_order" / "agent.can_refund_payment"
    without inventing a parallel permission system.

    Tool -> permission codename mapping lives in agent/tools/registry.py.
    """

    class Meta:
        managed = False  # no actual database table
        default_permissions = ()
        permissions = [
            ("can_read_user", "Can use agent tool: read user data"),
            ("can_read_product", "Can use agent tool: read product data"),
            ("can_read_order", "Can use agent tool: read order data"),
            ("can_read_payment", "Can use agent tool: read payment data"),
            ("can_read_crypto", "Can use agent tool: read crypto payment data"),
            ("can_cancel_order", "Can use agent tool: cancel an order"),
            ("can_refund_payment", "Can use agent tool: request a payment refund"),
            ("can_email_customer", "Can use agent tool: send a customer email"),
        ]

