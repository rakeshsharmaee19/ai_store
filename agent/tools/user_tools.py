"""Read-only tools exposing user data to the agent."""
from django.contrib.auth import get_user_model

from common.exceptions import ToolExecutionError

from .registry import ToolDefinition, registry

User = get_user_model()


def get_user(*, user_id: int) -> dict:
    user = User.objects.filter(id=user_id).first()
    if user is None:
        raise ToolExecutionError(f"No user found with id={user_id}.")
    return {
        "id": user.id,
        "email": user.email,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "is_active": user.is_active,
        "is_staff": user.is_staff,
        "date_joined": user.date_joined.isoformat(),
    }


registry.register(
    ToolDefinition(
        name="get_user",
        description="Get profile details of a single user by their numeric id.",
        parameters={
            "type": "object",
            "properties": {"user_id": {"type": "integer", "description": "The user's id."}},
            "required": ["user_id"],
        },
        handler=get_user,
        required_permission="agent.can_read_user",
        read_only=True,
        requires_confirmation=False,
    )
)
