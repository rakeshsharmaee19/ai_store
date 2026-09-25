"""Shared input validators."""
import re

from rest_framework import serializers

PASSWORD_MIN_LENGTH = 10
_PASSWORD_UPPER_RE = re.compile(r"[A-Z]")
_PASSWORD_LOWER_RE = re.compile(r"[a-z]")
_PASSWORD_DIGIT_RE = re.compile(r"\d")
_PASSWORD_SPECIAL_RE = re.compile(r"[^A-Za-z0-9]")


def validate_strong_password(value: str) -> str:
    errors = []
    if len(value) < PASSWORD_MIN_LENGTH:
        errors.append(f"Password must be at least {PASSWORD_MIN_LENGTH} characters long.")
    if not _PASSWORD_UPPER_RE.search(value):
        errors.append("Password must contain at least one uppercase letter.")
    if not _PASSWORD_LOWER_RE.search(value):
        errors.append("Password must contain at least one lowercase letter.")
    if not _PASSWORD_DIGIT_RE.search(value):
        errors.append("Password must contain at least one digit.")
    if not _PASSWORD_SPECIAL_RE.search(value):
        errors.append("Password must contain at least one special character.")
    if errors:
        raise serializers.ValidationError(errors)
    return value


def validate_positive_quantity(value: int) -> int:
    if value <= 0:
        raise serializers.ValidationError("Quantity must be a positive integer.")
    return value
