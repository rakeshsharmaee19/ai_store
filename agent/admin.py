from django.contrib import admin

from .models import AgentActionApproval, AgentConversation, AgentMessage, AgentToolCall


class AgentMessageInline(admin.TabularInline):
    model = AgentMessage
    extra = 0
    readonly_fields = ["role", "content", "created_at"]


@admin.register(AgentConversation)
class AgentConversationAdmin(admin.ModelAdmin):
    list_display = ["id", "user", "title", "status", "created_at"]
    inlines = [AgentMessageInline]


@admin.register(AgentToolCall)
class AgentToolCallAdmin(admin.ModelAdmin):
    list_display = ["id", "conversation", "tool_name", "status", "created_at"]
    list_filter = ["tool_name", "status"]


@admin.register(AgentActionApproval)
class AgentActionApprovalAdmin(admin.ModelAdmin):
    list_display = ["id", "action", "status", "requested_by", "approved_by", "created_at"]
    list_filter = ["action", "status"]
