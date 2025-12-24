# models.py
from django.db import models
from django.conf import settings
from utils.constants import PaymentStatus, DeliveryStatus, DeliveryItem
import uuid
from django.core.validators import MinValueValidator
import uuid
from datetime import datetime
import random
def generate_receipt_number():
    year = datetime.now().year
    random_digits = random.randint(100, 999)
    return f"HUX/{year}/{random_digits}"


class SalesReceipt(models.Model):
    """
    Sales Receipt for purchases
    """
    # Customer Information
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    customer_pan = models.CharField(max_length=20, blank=True, null=True)
    
    # Receipt Details
    receipt_number = models.CharField(
        max_length=50,
        unique=True,
        default=generate_receipt_number
    )
    
    # Product Information
    product_name = models.CharField(max_length=255)
    
    # Financial Information
    total_budget = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(0)]
    )
    paid_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    pending_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
        validators=[MinValueValidator(0)]
    )
    
    payment_status = models.CharField(
        max_length=20,
        choices=PaymentStatus.CHOICES,
        default=PaymentStatus.PENDING
    )
    
    # Additional Details
    description = models.TextField(blank=True, null=True)
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ('CASH', 'Cash'),
            ('UPI', 'UPI'),
            ('CARD', 'Card'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('CHEQUE', 'Cheque'),
            ('OTHER', 'Other'),
        ],
        default='CASH'
    )
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    
    # Created By
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='created_receipts'
    )
    
    # Status tracking
    is_receipt_issued = models.BooleanField(default=False)
    receipt_issued_date = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    sale_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'sales_receipts'
        verbose_name = 'Sales Receipt'
        verbose_name_plural = 'Sales Receipts'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.receipt_number} - {self.customer_name}"
    
    def save(self, *args, **kwargs):
        # Calculate pending amount
        self.pending_amount = self.total_budget - self.paid_amount
        
        # Update payment status based on amounts
        if self.paid_amount >= self.total_budget:
            self.payment_status = PaymentStatus.COMPLETED
        elif self.paid_amount > 0:
            self.payment_status = PaymentStatus.PARTIAL
        else:
            self.payment_status = PaymentStatus.PENDING
            
        super().save(*args, **kwargs)
    
    def issue_receipt(self):
        """Mark receipt as issued"""
        from django.utils import timezone
        self.is_receipt_issued = True
        self.receipt_issued_date = timezone.now()
        self.save()


class DeliveryServiceItem(models.Model):
    """
    Service delivery items with status tracking
    """
    SERVICE_TYPES = [
        ('WEBSITE', 'Website'),
        ('LOGO', 'Logo'),
        ('SOCIAL_MEDIA', 'Social Media Accounts'),
        ('MARKETING_MATERIAL', 'Marketing Material'),
        ('OTHER', 'Other Custom Services'),
    ]
    
    receipt = models.ForeignKey(
        SalesReceipt,
        on_delete=models.CASCADE,
        related_name='service_items'
    )
    
    service_type = models.CharField(
        max_length=50,
        choices=SERVICE_TYPES
    )
    
    service_name = models.CharField(max_length=255)
    description = models.TextField(blank=True, null=True)
    
    status = models.CharField(
        max_length=20,
        choices=DeliveryStatus.CHOICES,
        default=DeliveryStatus.PENDING
    )
    
    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_service_items'
    )
    
    # Completion
    is_completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    completion_notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'delivery_service_items'
        verbose_name = 'Delivery Service Item'
        verbose_name_plural = 'Delivery Service Items'
        ordering = ['created_at']
    
    def __str__(self):
        return f"{self.service_name} - {self.get_status_display()}"
    
    def mark_completed(self, notes=""):
        """Mark service item as completed"""
        from django.utils import timezone
        self.status = DeliveryStatus.COMPLETED
        self.is_completed = True
        self.completed_at = timezone.now()
        self.completion_notes = notes
        self.save()


class ReceiptPayment(models.Model):
    """
    Track individual payments for receipts
    """
    receipt = models.ForeignKey(
        SalesReceipt,
        on_delete=models.CASCADE,
        related_name='payments'
    )
    
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_method = models.CharField(
        max_length=50,
        choices=[
            ('CASH', 'Cash'),
            ('UPI', 'UPI'),
            ('CARD', 'Card'),
            ('BANK_TRANSFER', 'Bank Transfer'),
            ('CHEQUE', 'Cheque'),
            ('OTHER', 'Other'),
        ]
    )
    
    payment_reference = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Created By
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    
    payment_date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'receipt_payments'
        verbose_name = 'Receipt Payment'
        verbose_name_plural = 'Receipt Payments'
        ordering = ['-payment_date']
    
    def __str__(self):
        return f"Payment of ₹{self.amount} for {self.receipt.receipt_number}"