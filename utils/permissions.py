from rest_framework import permissions
from utils.constants import UserRole


class IsSuperAdmin(permissions.BasePermission):
    """
    Permission class to check if user is Super Admin
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.SUPER_ADMIN


class IsTeamLeader(permissions.BasePermission):
    """
    Permission class to check if user is Team Leader
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.TEAM_LEADER


class IsFranchiseCaller(permissions.BasePermission):
    """
    Permission class to check if user is Franchise Caller
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.FRANCHISE_CALLER


class IsPackageCaller(permissions.BasePermission):
    """
    Permission class to check if user is Package Caller
    """
    def has_permission(self, request, view):
        return request.user and request.user.is_authenticated and request.user.role == UserRole.PACKAGE_CALLER


class IsTeamLeaderOrSuperAdmin(permissions.BasePermission):
    """
    Permission class to check if user is Team Leader or Super Admin
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in [UserRole.TEAM_LEADER, UserRole.SUPER_ADMIN]
        )


class IsCallerOrAbove(permissions.BasePermission):
    """
    Permission class for Callers, Team Leader, and Super Admin
    """
    def has_permission(self, request, view):
        return (
            request.user and 
            request.user.is_authenticated and 
            request.user.role in [
                UserRole.FRANCHISE_CALLER,
                UserRole.PACKAGE_CALLER,
                UserRole.TEAM_LEADER,
                UserRole.SUPER_ADMIN
            ]
        )
    
from rest_framework import permissions
from utils.constants import UserRole


# ... (Keep your existing permission classes as they are)

class CanCreateUser(permissions.BasePermission):
    """
    Permission to check if user can create other users
    """
    def has_permission(self, request, view):
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = request.user.role
        
        # Super Admin can create all roles
        if user_role == UserRole.SUPER_ADMIN:
            return True
        
        # Team Leader can only create Package Caller and Franchise Caller
        if user_role == UserRole.TEAM_LEADER:
            # Check the role being created in request data
            role_to_create = request.data.get('role')
            if role_to_create:
                return role_to_create in [
                    UserRole.PACKAGE_CALLER,
                    UserRole.FRANCHISE_CALLER
                ]
            return True  # Allow if no role specified (will use default)
        
        # No other roles can create users
        return False


class CanUpdateUser(permissions.BasePermission):
    """
    Permission to check if user can update other users
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = request.user.role
        target_role = obj.role
        
        # Users can always update themselves
        if request.user.id == obj.id:
            return True
        
        # Super Admin can update all users
        if user_role == UserRole.SUPER_ADMIN:
            return True
        
        # Team Leader can update Package Caller and Franchise Caller
        # But cannot update other Team Leaders or Super Admin
        if user_role == UserRole.TEAM_LEADER:
            return target_role in [
                UserRole.PACKAGE_CALLER,
                UserRole.FRANCHISE_CALLER
            ]
        
        # No other roles can update users
        return False


class CanDeleteUser(permissions.BasePermission):
    """
    Permission to check if user can delete other users
    """
    def has_object_permission(self, request, view, obj):
        if not request.user or not request.user.is_authenticated:
            return False
        
        user_role = request.user.role
        target_role = obj.role
        
        # Super Admin can delete all users except themselves
        if user_role == UserRole.SUPER_ADMIN:
            return request.user.id != obj.id
        
        # Team Leader can delete Package Caller and Franchise Caller
        if user_role == UserRole.TEAM_LEADER:
            return target_role in [
                UserRole.PACKAGE_CALLER,
                UserRole.FRANCHISE_CALLER
            ]
        
        # No other roles can delete users
        return False
    
class IsOwnerOrHigher(permissions.BasePermission):
    """
    Allow users to access their own profile or higher roles to access others.
    """
    def has_object_permission(self, request, view, obj):
        # User can always access their own profile
        if obj == request.user:
            return True
        
        # Super Admin can access all
        if request.user.is_super_admin:
            return True
        
        # Team Leader can access Package Caller and Franchise Caller
        if request.user.is_team_leader:
            return obj.role in ['PACKAGE_CALLER', 'FRANCHISE_CALLER']
        
        # Others can only access their own profile
        return False