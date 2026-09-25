from django.urls import path

from .views import (
    AgentChatView,
    AgentConversationDetailView,
    ApprovalListView,
    ApproveActionView,
    RejectActionView,
)

urlpatterns = [
    path("chat/", AgentChatView.as_view(), name="agent-chat"),
    path("conversations/<int:pk>/", AgentConversationDetailView.as_view(), name="agent-conversation-detail"),
    path("approvals/", ApprovalListView.as_view(), name="agent-approval-list"),
    path("approvals/<int:pk>/approve/", ApproveActionView.as_view(), name="agent-approval-approve"),
    path("approvals/<int:pk>/reject/", RejectActionView.as_view(), name="agent-approval-reject"),
]
