from rest_framework.permissions import BasePermission


class IsOrderOwnerOrStaff(BasePermission):
    def has_object_permission(self, request, view, obj) -> bool:
        return request.user.is_staff or obj.user_id == request.user.id
