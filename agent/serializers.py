from rest_framework import serializers

from .models import AgentActionApproval, AgentConversation, AgentMessage, AgentToolCall


class AgentMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentMessage
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = fields


class AgentToolCallSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentToolCall
        fields = ["id", "tool_name", "arguments", "result", "status", "error", "created_at"]
        read_only_fields = fields


class AgentConversationSerializer(serializers.ModelSerializer):
    messages = AgentMessageSerializer(many=True, read_only=True)
    tool_calls = AgentToolCallSerializer(many=True, read_only=True)

    class Meta:
        model = AgentConversation
        fields = ["id", "title", "status", "messages", "tool_calls", "created_at", "updated_at"]
        read_only_fields = fields


class ChatRequestSerializer(serializers.Serializer):
    message = serializers.CharField()
    conversation_id = serializers.IntegerField(required=False, allow_null=True)


class ApprovalActionSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class AgentActionApprovalSerializer(serializers.ModelSerializer):
    class Meta:
        model = AgentActionApproval
        fields = [
            "id", "conversation", "action", "arguments", "requested_by", "approved_by",
            "status", "result", "error", "created_at", "approved_at",
        ]
        read_only_fields = fields
