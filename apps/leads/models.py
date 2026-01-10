from django.db import models

# Create your models here.
from django.db import models
from django.conf import settings
from utils.constants import LeadType, LeadStatus
from django.core.validators import MinLengthValidator, EmailValidator,RegexValidator

class Lead(models.Model):
    """
    Lead model for storing customer lead information
    """
    # Basic Information
    name = models.CharField(
        max_length=255,
        validators=[MinLengthValidator(2, "Name must be at least 2 characters")]
    )
    
    email = models.EmailField(
        blank=True, 
        null=True,
        validators=[EmailValidator(message="Enter a valid email address")]
    )
    
    phone = models.CharField(
        max_length=15,
        validators=[
            RegexValidator(
                regex=r'^[0-9+]{10,15}$',
                message="Phone number must be 10-15 digits"
            )
        ]
    )
    company = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    
    # Lead Classification
    lead_type = models.CharField(
        max_length=20,
        choices=LeadType.CHOICES,
        default=LeadType.FRANCHISE
    )
    status = models.CharField(
        max_length=20,
        choices=LeadStatus.CHOICES,
        default=LeadStatus.NEW
    )
    
    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_leads'
    )
    
    # Upload Information
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='uploaded_leads'
    )
    
    # Conversion Tracking
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='converted_leads'
    )
    converted_at = models.DateTimeField(null=True, blank=True)
    original_type = models.CharField(
        max_length=20,
        choices=LeadType.CHOICES,
        null=True,
        blank=True,
        help_text="Original lead type before conversion"
    )
    
    # Additional Information
    notes = models.TextField(blank=True, null=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'leads'
        verbose_name = 'Lead'
        verbose_name_plural = 'Leads'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['lead_type', 'status']),
            models.Index(fields=['assigned_to', 'status']),
        ]
    
    def __str__(self):
        return f"{self.name} - {self.get_lead_type_display()} ({self.get_status_display()})"


class LeadActivity(models.Model):
    """
    Track all activities/interactions with a lead
    """
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name='activities'
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True
    )
    
    activity_type = models.CharField(
        max_length=50,
        choices=[
            ('CALL', 'Call'),
            ('EMAIL', 'Email'),
            ('MEETING', 'Meeting'),
            ('NOTE', 'Note'),
            ('STATUS_CHANGE', 'Status Change'),
            ('CONVERSION', 'Conversion'),
        ]
    )
    
    description = models.TextField()
    old_status = models.CharField(max_length=20, blank=True, null=True)
    new_status = models.CharField(max_length=20, blank=True, null=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        db_table = 'lead_activities'
        verbose_name = 'Lead Activity'
        verbose_name_plural = 'Lead Activities'
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.lead.name} - {self.activity_type} at {self.created_at}"


class FollowUp(models.Model):
    """
    Schedule follow-ups for leads
    """
    lead = models.ForeignKey(
        Lead,
        on_delete=models.CASCADE,
        related_name='followups'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='followups'
    )
    
    scheduled_date = models.DateTimeField()
    notes = models.TextField(blank=True, null=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'followups'
        verbose_name = 'Follow Up'
        verbose_name_plural = 'Follow Ups'
        ordering = ['scheduled_date']
    
    def __str__(self):
        return f"Follow up for {self.lead.name} on {self.scheduled_date}"
    
# Add to models.py (after existing models, don't modify existing ones)

class PulledLead(models.Model):
    """
    Store leads that have been pulled out from callers
    Note: Original leads remain unchanged in Lead table
    """
    # Reference to original lead (optional)
    original_lead_id = models.IntegerField(null=True, blank=True, help_text="ID of the original lead before deletion")
    
    # Lead data (copied from original)
    name = models.CharField(max_length=255)
    email = models.EmailField(blank=True, null=True)
    phone = models.CharField(max_length=15, db_index=True)
    company = models.CharField(max_length=255, blank=True, null=True)
    city = models.CharField(max_length=100, blank=True, null=True)
    state = models.CharField(max_length=100, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    
    # Lead classification from original
    original_lead_type = models.CharField(max_length=20, choices=LeadType.CHOICES)
    original_status = models.CharField(max_length=20, choices=LeadStatus.CHOICES)
    
    # Pull metadata
    pulled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='pulled_leads'
    )
    pulled_from = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='leads_pulled_from'
    )
    pull_reason = models.TextField(blank=True, null=True)
    
    # Filter criteria used for pulling
    filter_criteria = models.JSONField(
        default=dict,
        blank=True,
        help_text="Stores the filter criteria used for pulling"
    )
    
    # Track if exported/downloaded
    exported = models.BooleanField(default=False)
    exported_at = models.DateTimeField(null=True, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'pulled_leads'
        verbose_name = 'Pulled Lead'
        verbose_name_plural = 'Pulled Leads'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone']),
            models.Index(fields=['pulled_by']),
            models.Index(fields=['pulled_from']),
            models.Index(fields=['original_status']),
            models.Index(fields=['original_lead_type']),
            models.Index(fields=['created_at']),
            models.Index(fields=['original_lead_id']),  # New index
        ]
    
    def __str__(self):
        return f"{self.name} - {self.phone} (Pulled)"