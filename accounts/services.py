"""Account-related business logic kept out of views/serializers."""
from django.contrib.auth import get_user_model

User = get_user_model()


def register_user(*, email: str, password: str, first_name: str = "", last_name: str = "") -> User:
    """Create a new user. Raises ValueError on duplicate email (serializer normally
    catches this first, but the service enforces the rule independently)."""
    email = email.strip().lower()
    if User.objects.filter(email=email).exists():
        raise ValueError("A user with this email already exists.")
    return User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name
    )
