import random
from datetime import timedelta

from django.db import models
from django.utils import timezone
from django.core.validators import RegexValidator, validate_email
from django.contrib.auth.models import AbstractUser

from utils.constants import UserRole


class OTP(models.Model):
    user = models.ForeignKey(
        'User',
        on_delete=models.CASCADE,
        related_name='otps'
    )
    otp = models.CharField(max_length=6)
    created_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)

    class Meta:
        db_table = 'otps'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.email} - {self.otp}"

    def is_valid(self):
        return not self.is_used and timezone.now() < self.expires_at

    @staticmethod
    def generate_otp():
        return str(random.randint(100000, 999999))


class User(AbstractUser):
    """
    Custom User model (email login, username hidden)
    """

    email = models.EmailField(
        unique=True,
        validators=[validate_email]
    )

    role = models.CharField(
        max_length=20,
        choices=UserRole.CHOICES,
        default=UserRole.FRANCHISE_CALLER
    )

    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'."
    )
    phone = models.CharField(
        validators=[phone_regex],
        max_length=15,
        blank=True,
        null=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 🔑 Email-based login
    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]  # required internally by Django

    class Meta:
        db_table = 'users'
        ordering = ['-created_at']

    def __str__(self):
        return self.email

    def create_otp(self):
        OTP.objects.filter(user=self, is_used=False).delete()

        otp_code = OTP.generate_otp()
        OTP.objects.create(
            user=self,
            otp=otp_code,
            expires_at=timezone.now() + timedelta(minutes=10)
        )

        return otp_code
