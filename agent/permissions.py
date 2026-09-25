"""
DRF permissions for the agent's own HTTP endpoints (chat, approvals).
Fine-grained per-TOOL authorization (e.g. "can this user call get_order?")
lives in agent/tools/registry.py and is enforced by the executor -- that is
the real security boundary the LLM cannot bypass.
"""
from rest_framework.permissions import BasePermission


class IsSupportOrAdmin(BasePermission):
    """
    Only authenticated staff users may talk to the agent at all. Individual
    tools are further gated by Django permissions checked in the executor.
    """

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class CanApproveAgentActions(BasePermission):
    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)
