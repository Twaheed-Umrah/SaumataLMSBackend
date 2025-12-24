# views.py
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import TokenError
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.views import APIView
from rest_framework import status
from django.db.models import Count, Q
from utils.constants import UserRole
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
import logging

from utils.response import success_response, error_response

logger = logging.getLogger(__name__)
from .models import User, OTP
from .serializers import (
    UserSerializer,
    UserCreateSerializer,
    UserUpdateSerializer,
    ChangePasswordSerializer,
    LoginSerializer,
    ForgotPasswordSerializer,
    VerifyOTPSerializer,
    ResetPasswordSerializer,
    TokenRefreshSerializer
)

from utils.permissions import IsSuperAdmin, IsTeamLeaderOrSuperAdmin, IsOwnerOrHigher
from utils.response import success_response, error_response, created_response


class UserViewSet(viewsets.ModelViewSet):
    """
    ViewSet for User CRUD operations and authentication (JWT Version)
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer

    # -------------------------
    # Permissions
    # -------------------------
    def get_permissions(self):
        if self.action in ['login', 'refresh_token', 'forgot_password', 'verify_otp', 'reset_password']:
            permission_classes = [AllowAny]
        elif self.action == 'create':
            # Only Team Leader or Super Admin can create users
            permission_classes = [IsTeamLeaderOrSuperAdmin]
        elif self.action == 'destroy':
            # Only Super Admin or Team Leader can delete based on role
            permission_classes = [IsTeamLeaderOrSuperAdmin]
        elif self.action in ['update', 'partial_update']:
            # Users can update their own profile, higher roles can update others
            permission_classes = [IsAuthenticated, IsOwnerOrHigher]
        elif self.action in ['list', 'retrieve']:
            # List: Team Leader/Super Admin, Retrieve: Own profile or higher
            permission_classes = [IsAuthenticated, IsOwnerOrHigher]
        elif self.action in ['logout', 'me', 'change_password']:
            permission_classes = [IsAuthenticated]
        else:
            permission_classes = [IsAuthenticated]
        
        return [permission() for permission in permission_classes]

    # -------------------------
    # Serializer Selection
    # -------------------------
    def get_serializer_class(self):
        if self.action == 'create':
            return UserCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return UserUpdateSerializer
        elif self.action == 'login':
            return LoginSerializer
        elif self.action == 'forgot_password':
            return ForgotPasswordSerializer
        elif self.action == 'verify_otp':
            return VerifyOTPSerializer
        elif self.action == 'reset_password':
            return ResetPasswordSerializer
        elif self.action == 'refresh_token':
            return TokenRefreshSerializer
        return UserSerializer

    # -------------------------
    # Queryset Restriction
    # -------------------------
    def get_queryset(self):
        """
        Restrict user visibility based on role
        """
        user = self.request.user

        if not user.is_authenticated:
            return User.objects.none()

        if user.role == 'SUPER_ADMIN':
            return User.objects.all()

        if user.role == 'TEAM_LEADER':
            # Team Leader can see all except Super Admin
            return User.objects.exclude(role='SUPER_ADMIN')

        # Regular users can only see themselves
        return User.objects.filter(id=user.id)

    # -------------------------
    # CRUD Overrides with permission checks
    # -------------------------
    def list(self, request, *args, **kwargs):
        users = self.get_queryset()
        serializer = self.get_serializer(users, many=True)
        return success_response(serializer.data, "Users retrieved successfully")

    def create(self, request, *args, **kwargs):
        """
        Create user with role-based restrictions
        """
        user = request.user
        requested_role = request.data.get('role')
        
        # Validate role assignment permissions
        if requested_role:
            if user.role == 'TEAM_LEADER':
                # Team Leader can only create Package Caller and Franchise Caller
                if requested_role not in ['PACKAGE_CALLER', 'FRANCHISE_CALLER']:
                    return error_response(
                        "Team Leader can only create Package Caller or Franchise Caller",
                        status_code=status.HTTP_403_FORBIDDEN
                    )
            elif user.role != 'SUPER_ADMIN':
                return error_response(
                    "You don't have permission to create users",
                    status_code=status.HTTP_403_FORBIDDEN
                )
        
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user_instance = serializer.save()
        
        return created_response(
            UserSerializer(user_instance).data,
            "User created successfully"
        )

    def update(self, request, *args, **kwargs):
        """
        Update user with role-based restrictions
        """
        instance = self.get_object()
        user = request.user
        
        # Check if user is trying to update role
        if 'role' in request.data and instance.role != request.data['role']:
            if user.role == 'TEAM_LEADER':
                # Team Leader can only update to Package Caller or Franchise Caller
                if request.data['role'] not in ['PACKAGE_CALLER', 'FRANCHISE_CALLER']:
                    return error_response(
                        "Team Leader can only assign Package Caller or Franchise Caller roles",
                        status_code=status.HTTP_403_FORBIDDEN
                    )
                # Team Leader cannot update other Team Leaders
                if instance.role == 'TEAM_LEADER':
                    return error_response(
                        "Team Leader cannot update other Team Leaders",
                        status_code=status.HTTP_403_FORBIDDEN
                    )
            
            elif user.role != 'SUPER_ADMIN':
                return error_response(
                    "You don't have permission to change roles",
                    status_code=status.HTTP_403_FORBIDDEN
                )
        
        serializer = self.get_serializer(instance, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        
        return success_response(
            UserSerializer(instance).data,
            "User updated successfully"
        )

    def destroy(self, request, *args, **kwargs):
        """
        Delete user with role-based restrictions
        """
        instance = self.get_object()
        user = request.user
        
        # Prevent self-deletion
        if instance == user:
            return error_response(
                "You cannot delete your own account",
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Super Admin can delete anyone
        if user.role == 'SUPER_ADMIN':
            instance.delete()
            return success_response(message="User deleted successfully")
        
        # Team Leader can only delete Package Caller and Franchise Caller
        if user.role == 'TEAM_LEADER':
            if instance.role in ['PACKAGE_CALLER', 'FRANCHISE_CALLER']:
                instance.delete()
                return success_response(message="User deleted successfully")
            else:
                return error_response(
                    "Team Leader can only delete Package Caller or Franchise Caller",
                    status_code=status.HTTP_403_FORBIDDEN
                )
        
        # Others cannot delete anyone
        return error_response(
            "You don't have permission to delete users",
            status_code=status.HTTP_403_FORBIDDEN
        )

    # -------------------------
    # AUTHENTICATION ACTIONS (JWT)
    # -------------------------
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def login(self, request):
        """
        Login using email & password (JWT Version)
        """
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        user = serializer.validated_data['user']
        refresh_token = serializer.validated_data['refresh']
        access_token = serializer.validated_data['access']
        
        return success_response(
            {
                'user': UserSerializer(user).data,
                'tokens': {
                    'refresh': refresh_token,
                    'access': access_token,
                }
            },
            "Login successful"
        )

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def logout(self, request):
        """
        Logout user (JWT Version)
        Note: JWT is stateless, so we just return success
        Frontend should delete tokens from storage
        """
        return success_response(
            message="Logout successful. Please delete tokens from client storage."
        )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def refresh_token(self, request):
        """
        Refresh access token using refresh token
        """
        serializer = TokenRefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        refresh_token = serializer.validated_data['refresh']
        
        try:
            refresh = RefreshToken(refresh_token)
            access_token = str(refresh.access_token)
            
            return success_response(
                {
                    'access': access_token
                },
                "Token refreshed successfully"
            )
        except TokenError as e:
            return error_response(
                f"Invalid refresh token: {str(e)}",
                status_code=status.HTTP_401_UNAUTHORIZED
            )

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        """
        Get current logged-in user
        """
        serializer = self.get_serializer(request.user)
        return success_response(serializer.data)

    @action(detail=False, methods=['post'], permission_classes=[IsAuthenticated])
    def change_password(self, request):
        """
        Change user password
        """
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user

        if not user.check_password(serializer.validated_data['old_password']):
            return error_response(
                {"old_password": "Old password is incorrect"},
                status_code=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data['new_password'])
        user.save()
        
        # Generate new tokens after password change
        refresh = RefreshToken.for_user(user)
        
        return success_response(
            {
                'tokens': {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            },
            "Password changed successfully. New tokens have been issued."
        )

    # -------------------------
    # PASSWORD RESET ACTIONS (OTP)
    # -------------------------
    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def forgot_password(self, request):
        """
        Step 1: Request OTP for password reset
        """
        serializer = ForgotPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email'].lower()
        
        try:
            user = User.objects.get(email=email)
            
            # Generate OTP
            otp_code = user.create_otp()
            
            # Send OTP via email
            try:
                # HTML email template for better appearance
                html_message = f"""
                <html>
                <body style="font-family: Arial, sans-serif;">
                    <h2>Password Reset Request</h2>
                    <p>Hello {user.first_name or user.username},</p>
                    <p>You have requested to reset your password.</p>
                    <div style="background-color: #f4f4f4; padding: 20px; margin: 20px 0; text-align: center;">
                        <h3 style="color: #333; margin: 0;">Your OTP Code</h3>
                        <h1 style="color: #007bff; font-size: 32px; letter-spacing: 5px; margin: 10px 0;">{otp_code}</h1>
                        <p style="color: #666;">This OTP is valid for 10 minutes.</p>
                    </div>
                    <p>If you didn't request this, please ignore this email.</p>
                    <p>Best regards,<br>Your Application Team</p>
                </body>
                </html>
                """
                
                send_mail(
                    subject='Password Reset OTP - Your Application',
                    message=f'Your OTP for password reset is: {otp_code}\nThis OTP is valid for 10 minutes.',
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    recipient_list=[email],
                    html_message=html_message,
                    fail_silently=False,
                )
            except Exception as e:
                # Log the error but still return success for security reasons
                print(f"Email sending failed: {e}")
            
            # Always return success even if email fails (for security)
            return success_response(
                {"message": "If the email exists, an OTP has been sent"},
                "OTP sent successfully"
            )
            
        except User.DoesNotExist:
            # For security reasons, don't reveal if user exists or not
            return success_response(
                {"message": "If the email exists, an OTP has been sent"},
                "OTP sent successfully"
            )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def verify_otp(self, request):
        """
        Step 2: Verify OTP
        """
        serializer = VerifyOTPSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        
        # Get the OTP object
        user = User.objects.get(email=email)
        otp_obj = OTP.objects.filter(
            user=user,
            otp=otp,
            is_used=False
        ).latest('created_at')
        
        return success_response(
            {
                "email": email,
                "otp": otp,
                "valid_until": otp_obj.expires_at
            },
            "OTP verified successfully"
        )

    @action(detail=False, methods=['post'], permission_classes=[AllowAny])
    def reset_password(self, request):
        """
        Step 3: Reset password with OTP verification
        """
        serializer = ResetPasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        email = serializer.validated_data['email']
        otp = serializer.validated_data['otp']
        new_password = serializer.validated_data['new_password']
        
        user = User.objects.get(email=email)
        
        # Get and validate OTP
        otp_obj = OTP.objects.filter(
            user=user,
            otp=otp,
            is_used=False
        ).latest('created_at')
        
        if not otp_obj.is_valid():
            return error_response(
                {"otp": "OTP has expired or is invalid"},
                status_code=status.HTTP_400_BAD_REQUEST
            )
        
        # Mark OTP as used
        otp_obj.is_used = True
        otp_obj.save()
        
        # Update password
        user.set_password(new_password)
        user.save()
        
        # Generate new tokens for immediate login
        refresh = RefreshToken.for_user(user)
        
        # Send confirmation email
        try:
            html_message = f"""
            <html>
            <body style="font-family: Arial, sans-serif;">
                <h2>Password Reset Successful</h2>
                <p>Hello {user.first_name or user.username},</p>
                <p>Your password has been reset successfully.</p>
                <p>If you didn't perform this action, please contact support immediately.</p>
                <p>Best regards,<br>Your Application Team</p>
            </body>
            </html>
            """
            
            send_mail(
                subject='Password Reset Successful - Your Application',
                message='Your password has been reset successfully.',
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[email],
                html_message=html_message,
                fail_silently=True,
            )
        except Exception as e:
            print(f"Confirmation email failed: {e}")
        
        return success_response(
            {
                "email": email,
                            },
            "Password reset successfully"
        )

class UserStatsAPIView(APIView):
    """
    Returns user statistics for dashboard
    """
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """
        Only Super Admin and Team Leader can access user stats
        """
        if self.request.user.role in ['SUPER_ADMIN', 'TEAM_LEADER']:
            return [IsAuthenticated()]
        return [IsAuthenticated()]  # Default - will be checked in get method

    def get(self, request, *args, **kwargs):
        try:
            # Check if user has permission to view stats
            if request.user.role not in ['SUPER_ADMIN', 'TEAM_LEADER']:
                return error_response(
                    "You don't have permission to view user statistics",
                    status_code=status.HTTP_403_FORBIDDEN
                )
            
            stats = self._calculate_stats()
            return success_response(stats, "Statistics retrieved successfully")
        except Exception as e:
            logger.error("Error fetching user stats", exc_info=True)
            return error_response(
                "Unable to retrieve statistics at this time",
                status_code=500
            )

    def _calculate_stats(self):
        """
        Optimized single-query stats
        """
        stats = User.objects.aggregate(
            total_users=Count("id"),
            active_users=Count(
                "id",
                filter=Q(is_active=True)
            ),
            inactive_users=Count(
                "id",
                filter=Q(is_active=False)
            ),
            super_admins=Count(
                "id",
                filter=Q(role=UserRole.SUPER_ADMIN)
            ),
            team_leaders=Count(
                "id",
                filter=Q(role=UserRole.TEAM_LEADER)
            ),
            franchise_callers=Count(
                "id",
                filter=Q(role=UserRole.FRANCHISE_CALLER)
            ),
            package_callers=Count(
                "id",
                filter=Q(role=UserRole.PACKAGE_CALLER)
            ),
        )

        # Add calculated fields
        stats['total_callers'] = stats['franchise_callers'] + stats['package_callers']
        
        return stats
    
class TeamMembersAPIView(APIView):
    """
    Returns team members based on logged-in user's role
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user

        # SUPER ADMIN → All users
        if user.role == UserRole.SUPER_ADMIN:
            queryset = User.objects.all()

        # TEAM LEADER → All users (optional: exclude SUPER_ADMIN)
        elif user.role == UserRole.TEAM_LEADER:
            queryset = User.objects.exclude(role=UserRole.SUPER_ADMIN)

        # FRANCHISE CALLER → All PACKAGE CALLERS
        elif user.role == UserRole.FRANCHISE_CALLER:
            queryset = User.objects.filter(role=UserRole.PACKAGE_CALLER)

        # PACKAGE CALLER → All FRANCHISE CALLERS
        elif user.role == UserRole.PACKAGE_CALLER:
            queryset = User.objects.filter(role=UserRole.FRANCHISE_CALLER)

        else:
            return error_response(
                "Invalid user role",
                status_code=status.HTTP_403_FORBIDDEN
            )

        serializer = UserSerializer(queryset, many=True)
        return success_response(
            serializer.data,
            "Team members retrieved successfully"
        )