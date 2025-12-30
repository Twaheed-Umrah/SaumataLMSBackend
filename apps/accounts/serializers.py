# serializers.py
from rest_framework import serializers
from django.core.exceptions import ValidationError
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.tokens import RefreshToken

from .models import User, OTP
from utils.constants import UserRole


class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for User model
    """
    role_display = serializers.CharField(source='get_role_display', read_only=True)
    
    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name',
            'phone', 'role', 'role_display', 'is_active', 
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class UserCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating users
    """
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True, min_length=8)

    class Meta:
        model = User
        fields = [
            'email', 'password', 'password_confirm',
            'first_name', 'last_name', 'phone', 'role'
        ]

    def validate(self, data):
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError({"password_confirm": "Passwords do not match"})
        
        # Validate password strength
        try:
            validate_password(data['password'])
        except ValidationError as e:
            raise serializers.ValidationError({"password": list(e.messages)})
            
        return data

    def create(self, validated_data):
        validated_data.pop('password_confirm')
        password = validated_data.pop('password')

        email = validated_data['email'].lower()
        username = email.split('@')[0]

        # ensure unique username
        base_username = username
        counter = 1
        while User.objects.filter(username=username).exists():
            username = f"{base_username}{counter}"
            counter += 1

        user = User.objects.create(
            username=username,
            **validated_data
        )
        user.set_password(password)
        user.save()
        return user


class UserUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating users
    """
    class Meta:
        model = User
        fields = [
            'email', 'first_name', 'last_name', 'phone', 
            'role', 'is_active'
        ]


class ChangePasswordSerializer(serializers.Serializer):
    """
    Serializer for password change
    """
    old_password = serializers.CharField(required=True, write_only=True)
    new_password = serializers.CharField(required=True, min_length=8, write_only=True)
    new_password_confirm = serializers.CharField(required=True, min_length=8, write_only=True)
    
    def validate(self, data):
        if data['new_password'] != data['new_password_confirm']:
            raise serializers.ValidationError({"new_password_confirm": "New passwords do not match"})
        
        # Validate password strength
        try:
            validate_password(data['new_password'])
        except ValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})
            
        return data


class LoginSerializer(serializers.Serializer):
    """
    Serializer for user login using email (JWT Version)
    """
    email = serializers.EmailField(required=True)
    password = serializers.CharField(write_only=True, required=True)

    def validate(self, data):
        email = data.get('email').lower()
        password = data.get('password')

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "Invalid email or password"})

        if not user.check_password(password):
            raise serializers.ValidationError({"password": "Invalid email or password"})

        if not user.is_active:
            raise serializers.ValidationError({"email": "User account is disabled"})

        # Generate JWT tokens
        refresh = RefreshToken.for_user(user)
        
        data['user'] = user
        data['refresh'] = str(refresh)
        data['access'] = str(refresh.access_token)
        
        return data


class ForgotPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    
    def validate_email(self, value):
        try:
            user = User.objects.get(email=value)
        except User.DoesNotExist:
            raise serializers.ValidationError("User with this email does not exist.")
        
        if not user.is_active:
            raise serializers.ValidationError("User account is inactive.")
        
        return value


class VerifyOTPSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(max_length=6, required=True)
    
    def validate(self, data):
        email = data.get('email')
        otp = data.get('otp')
        
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist."})
        
        try:
            otp_obj = OTP.objects.filter(
                user=user,
                otp=otp,
                is_used=False
            ).latest('created_at')
            
            if not otp_obj.is_valid():
                raise serializers.ValidationError({"otp": "OTP has expired or is invalid."})
            
        except OTP.DoesNotExist:
            raise serializers.ValidationError({"otp": "Invalid OTP."})
        
        return data


class ResetPasswordSerializer(serializers.Serializer):
    email = serializers.EmailField(required=True)
    otp = serializers.CharField(max_length=6, required=True)
    new_password = serializers.CharField(write_only=True, required=True, min_length=8)
    confirm_password = serializers.CharField(write_only=True, required=True, min_length=8)
    
    def validate(self, data):
        email = data.get('email')
        otp = data.get('otp')
        new_password = data.get('new_password')
        confirm_password = data.get('confirm_password')
        
        # Check password match
        if new_password != confirm_password:
            raise serializers.ValidationError({"confirm_password": "Passwords do not match."})
        
        # Validate password strength
        try:
            validate_password(new_password)
        except ValidationError as e:
            raise serializers.ValidationError({"new_password": list(e.messages)})
        
        # Verify user exists
        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            raise serializers.ValidationError({"email": "User with this email does not exist."})
        
        # Verify OTP
        try:
            otp_obj = OTP.objects.filter(
                user=user,
                otp=otp,
                is_used=False
            ).latest('created_at')
            
            if not otp_obj.is_valid():
                raise serializers.ValidationError({"otp": "OTP has expired or is invalid."})
            
        except OTP.DoesNotExist:
            raise serializers.ValidationError({"otp": "Invalid OTP."})
        
        return data


class TokenRefreshSerializer(serializers.Serializer):
    """
    Serializer for refreshing access token
    """
    refresh = serializers.CharField(required=True)

# In serializers.py, add this serializer
class AvailableCallerSerializer(serializers.ModelSerializer):
    """
    Serializer for available callers with lead count
    """
    name = serializers.SerializerMethodField()
    current_leads_count = serializers.IntegerField()
    
    class Meta:
        model = User
        fields = ['id', 'name', 'email', 'role', 'current_leads_count', 'is_active']
    
    def get_name(self, obj):
        return obj.get_full_name()