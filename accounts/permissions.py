from rest_framework.permissions import BasePermission


class IsStaffUser(BasePermission):
    """Allows access only to staff/admin users."""

    def has_permission(self, request, view) -> bool:
        return bool(request.user and request.user.is_authenticated and request.user.is_staff)


class IsOwnerOrStaff(BasePermission):
    """Object-level permission: only the owner of a resource, or staff, may access it."""

    owner_field = "user"

    def has_object_permission(self, request, view, obj) -> bool:
        if request.user.is_staff:
            return True
        owner = getattr(obj, self.owner_field, None)
        return owner is not None and owner == request.user
