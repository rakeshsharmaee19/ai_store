"""Small shared helper utilities used across apps."""
import uuid


def generate_order_number() -> str:
    return f"ORD-{uuid.uuid4().hex[:10].upper()}"


def generate_idempotency_key() -> str:
    return uuid.uuid4().hex


def mask_sensitive(value: str, visible_chars: int = 4) -> str:
    """Mask a sensitive string, keeping only the last `visible_chars` visible."""
    if not value:
        return value
    if len(value) <= visible_chars:
        return "*" * len(value)
    return "*" * (len(value) - visible_chars) + value[-visible_chars:]


def get_client_ip(request) -> str | None:
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
