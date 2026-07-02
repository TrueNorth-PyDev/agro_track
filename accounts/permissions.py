"""
DRF permission classes for AgroTrack role-based access control (RBAC).

Usage in views:
    permission_classes = [IsAuthenticated, IsDispatcher]

These classes check the `role` field on the authenticated User model.
They can be combined with DRF's built-in `IsAuthenticated`.
"""

from rest_framework.permissions import BasePermission


class IsSender(BasePermission):
    """
    Grants access only to users with the 'sender' role.
    Senders can create orders, view status, and access POD.
    """
    message = 'Access restricted to Sender / Receiver accounts.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'sender'
        )


class IsDispatcher(BasePermission):
    """
    Grants access only to users with the 'dispatcher' role.
    Dispatchers manage the order queue and assign drivers/vehicles.
    """
    message = 'Access restricted to Logistics Dispatcher accounts.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'dispatcher'
        )


class IsAdminUser(BasePermission):
    """
    Grants access only to users with the 'admin' role.
    Admins manage users, RBAC, and master data.

    Note: This is distinct from Django's `is_staff` flag, which only
    controls access to the Django admin site.
    """
    message = 'Access restricted to Platform Admin accounts.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role == 'admin'
        )


class IsDispatcherOrAdmin(BasePermission):
    """
    Grants access to both dispatchers and admins.
    Used for shared management views.
    """
    message = 'Access restricted to Dispatcher or Admin accounts.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('dispatcher', 'admin')
        )


class IsSenderOrAdmin(BasePermission):
    """
    Grants access to both senders and admins.
    Used for order-related views where admin oversight is needed.
    """
    message = 'Access restricted to Sender or Admin accounts.'

    def has_permission(self, request, view):
        return (
            request.user
            and request.user.is_authenticated
            and request.user.role in ('sender', 'admin')
        )
