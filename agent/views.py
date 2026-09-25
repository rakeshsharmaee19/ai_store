import logging

from django.core.cache import cache
from django.conf import settings
from django.db import transaction
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from common.constants import APPROVAL_APPROVED, APPROVAL_EXECUTED, APPROVAL_FAILED, APPROVAL_PENDING, APPROVAL_REJECTED
from common.exceptions import ApplicationError, RateLimitExceeded, UnauthorizedAction
from common.utils import get_client_ip

from .models import AgentActionApproval, AgentConversation
from .permissions import CanApproveAgentActions, IsSupportOrAdmin
from .serializers import (
    AgentActionApprovalSerializer,
    AgentConversationSerializer,
    ApprovalActionSerializer,
    ChatRequestSerializer,
)
from .services.agent_service import AgentService

logger = logging.getLogger("agent")


def _check_rate_limit(user) -> None:
    key = f"agent:ratelimit:{user.id}"
    current = cache.get(key)
    if current is not None and current >= settings.AGENT_RATE_LIMIT_PER_MINUTE:
        raise RateLimitExceeded(
            f"Rate limit of {settings.AGENT_RATE_LIMIT_PER_MINUTE} requests/minute exceeded."
        )
    if current is None:
        cache.set(key, 1, timeout=60)
    else:
        cache.incr(key)


class AgentChatView(APIView):
    """POST /api/agent/chat/"""

    permission_classes = [IsSupportOrAdmin]

    def post(self, request):
        _check_rate_limit(request.user)

        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        conversation = None
        conversation_id = serializer.validated_data.get("conversation_id")
        if conversation_id:
            conversation = AgentConversation.objects.filter(id=conversation_id, user=request.user).first()
            if conversation is None:
                raise UnauthorizedAction("Conversation not found or not owned by you.")

        result = AgentService().handle_message(
            user=request.user, conversation=conversation, message=serializer.validated_data["message"]
        )
        return Response(result, status=status.HTTP_200_OK)


class AgentConversationDetailView(APIView):
    """GET /api/agent/conversations/{id}/ - inspect full transcript + tool calls."""

    permission_classes = [IsSupportOrAdmin]

    def get(self, request, pk):
        conversation = AgentConversation.objects.filter(id=pk, user=request.user).first()
        if conversation is None:
            raise UnauthorizedAction("Conversation not found or not owned by you.")
        return Response(AgentConversationSerializer(conversation).data)


class ApprovalListView(APIView):
    """GET /api/agent/approvals/ - list pending (and other) approvals, staff-only."""

    permission_classes = [CanApproveAgentActions]

    def get(self, request):
        qs = AgentActionApproval.objects.all()
        status_filter = request.query_params.get("status")
        if status_filter:
            qs = qs.filter(status=status_filter)
        return Response(AgentActionApprovalSerializer(qs, many=True).data)


class ApproveActionView(APIView):
    """
    POST /api/agent/approvals/{id}/approve/

    Executes the underlying action through the real Django service layer
    (e.g. PaymentService.refund_payment), never through the LLM. Idempotent:
    calling approve twice on an already-executed approval is a safe no-op.
    """

    permission_classes = [CanApproveAgentActions]

    @transaction.atomic
    def post(self, request, pk):
        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval = AgentActionApproval.objects.select_for_update().get(id=pk)

        if approval.status == APPROVAL_EXECUTED:
            return Response(AgentActionApprovalSerializer(approval).data)  # idempotent replay

        if approval.status != APPROVAL_PENDING:
            raise UnauthorizedAction(f"Approval is in status '{approval.status}' and cannot be approved.")

        from django.utils import timezone

        approval.status = APPROVAL_APPROVED
        approval.approved_by = request.user
        approval.approved_at = timezone.now()
        approval.save(update_fields=["status", "approved_by", "approved_at"])

        try:
            result = self._execute_action(approval, request)
            approval.status = APPROVAL_EXECUTED
            approval.result = result
            approval.save(update_fields=["status", "result"])
        except ApplicationError as exc:
            approval.status = APPROVAL_FAILED
            approval.error = exc.message
            approval.save(update_fields=["status", "error"])
            raise

        return Response(AgentActionApprovalSerializer(approval).data)

    def _execute_action(self, approval: AgentActionApproval, request) -> dict:
        from payments.models import PaymentTransaction
        from payments.services import refund_payment, write_audit_log

        if approval.action == "refund_payment":
            payment = PaymentTransaction.objects.get(id=approval.arguments["payment_id"])
            refund = refund_payment(
                payment=payment,
                actor=request.user,
                reason=approval.arguments.get("reason", ""),
            )
            write_audit_log(
                actor=request.user,
                action="AGENT_APPROVAL_EXECUTED",
                resource_type="AgentActionApproval",
                resource_id=approval.id,
                metadata={"payment_id": payment.id},
                ip_address=get_client_ip(request),
            )
            return {"refund_id": refund.id, "amount": str(refund.amount)}

        raise ApplicationError(f"Unknown approval action '{approval.action}'.", code="UNKNOWN_ACTION")


class RejectActionView(APIView):
    """POST /api/agent/approvals/{id}/reject/"""

    permission_classes = [CanApproveAgentActions]

    def post(self, request, pk):
        serializer = ApprovalActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        approval = AgentActionApproval.objects.get(id=pk)
        if approval.status != APPROVAL_PENDING:
            raise UnauthorizedAction(f"Approval is in status '{approval.status}' and cannot be rejected.")

        approval.status = APPROVAL_REJECTED
        approval.approved_by = request.user
        approval.error = serializer.validated_data.get("note", "")
        approval.save(update_fields=["status", "approved_by", "error"])
        return Response(AgentActionApprovalSerializer(approval).data)
