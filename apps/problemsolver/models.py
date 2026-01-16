from django.db import models
from django.contrib.auth import get_user_model
from django.utils import timezone
from django.conf import settings

class ProblemReport(models.Model):
    """
    Comprehensive problem tracking system for tour and travels company
    """
    PROBLEM_STATUS = [
        ('PENDING', 'Pending'),
        ('IN_PROGRESS', 'In Progress'),
        ('RESOLVED', 'Resolved'),
        ('ESCALATED', 'Escalated'),
        ('CANCELLED', 'Cancelled'),
    ]
    
    PRIORITY_LEVELS = [
        ('LOW', 'Low'),
        ('MEDIUM', 'Medium'),
        ('HIGH', 'High'),
        ('URGENT', 'Urgent'),
    ]
    
    # PROBLEM_TYPES specific to tour and travels company
    PROBLEM_TYPES = [
        ('BOOKING', 'Booking Issue'),
        ('PAYMENT', 'Payment/Pricing Issue'),
        ('CANCELLATION', 'Cancellation/Refund Issue'),
        ('ITINERARY', 'Itinerary/Planning Issue'),
        ('ACCOMMODATION', 'Accommodation/Hotel Issue'),
        ('TRANSPORT', 'Transport/Vehicle Issue'),
        ('GUIDE', 'Guide/Staff Issue'),
        ('VISA', 'Visa/Documentation Issue'),
        ('FOOD_CATERING', 'Food/Catering Issue'),
        ('HEALTH_SAFETY', 'Health/Safety Concern'),
        ('COMMUNICATION', 'Communication Issue'),
        ('CUSTOMER_SERVICE', 'Customer Service Issue'),
        ('WEATHER', 'Weather Related Issue'),
        ('OTHER', 'Other Issue'),
    ]
    
    # Problem Information
    title = models.CharField(max_length=255)
    description = models.TextField()
    problem_type = models.CharField(
        max_length=50,
        choices=PROBLEM_TYPES,
        default='OTHER'
    )
    priority = models.CharField(
        max_length=20,
        choices=PRIORITY_LEVELS,
        default='MEDIUM'
    )
    status = models.CharField(
        max_length=20,
        choices=PROBLEM_STATUS,
        default='PENDING'
    )
    
    # Customer Information
    customer_name = models.CharField(max_length=255)
    customer_email = models.EmailField()
    customer_phone = models.CharField(max_length=20)
    
    # Tour Information
    tour_package = models.CharField(max_length=200, blank=True, null=True)
    travel_date = models.DateField(blank=True, null=True)
    
    # Assignment
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_problems'
    )
    reported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name='reported_problems'
    )
    
    # Dates
    reported_date = models.DateTimeField(default=timezone.now)
    due_date = models.DateField(null=True, blank=True)
    resolved_date = models.DateTimeField(null=True, blank=True)
    
    # Resolution
    resolution_notes = models.TextField(blank=True, null=True)
    resolution_time_minutes = models.IntegerField(null=True, blank=True)
    is_resolved = models.BooleanField(default=False)
    
    # Communication History (stores all updates as JSON)
    communication_history = models.JSONField(default=list, blank=True)
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'problem_reports'
        verbose_name = 'Problem Report'
        verbose_name_plural = 'Problem Reports'
        ordering = ['-reported_date']
        indexes = [
            models.Index(fields=['status', 'priority']),
            models.Index(fields=['reported_date']),
            models.Index(fields=['assigned_to', 'status']),
            models.Index(fields=['customer_email']),
            models.Index(fields=['customer_name']),
        ]
    
    def __str__(self):
        return f"{self.title} - {self.customer_name} ({self.get_status_display()})"
    
    def save(self, *args, **kwargs):
        # Auto-set is_resolved based on status
        if self.status == 'RESOLVED' and not self.is_resolved:
            self.is_resolved = True
            self.resolved_date = timezone.now()
            
            # Calculate resolution time if not already set
            if not self.resolution_time_minutes and self.resolved_date and self.reported_date:
                time_diff = self.resolved_date - self.reported_date
                self.resolution_time_minutes = int(time_diff.total_seconds() / 60)
        
        elif self.status != 'RESOLVED' and self.is_resolved:
            self.is_resolved = False
            self.resolved_date = None
        
        super().save(*args, **kwargs)
    
    def add_communication(self, message, user=None, is_internal=False, new_status=None):
        """Add communication to history"""
        communication = {
            'timestamp': timezone.now().isoformat(),
            'message': message,
            'user_id': user.id if user else None,
            'user_name': user.get_full_name() if user else 'System',
            'is_internal': is_internal,
            'new_status': new_status
        }
        
        if not self.communication_history:
            self.communication_history = []
        
        self.communication_history.append(communication)
        
        # Keep only last 100 communications
        if len(self.communication_history) > 100:
            self.communication_history = self.communication_history[-100:]
        
        self.save(update_fields=['communication_history'])
    
    def mark_resolved(self, resolution_notes="", resolved_by=None):
        """Mark problem as resolved"""
        self.status = 'RESOLVED'
        self.resolution_notes = resolution_notes
        self.is_resolved = True
        self.resolved_date = timezone.now()
        
        # Add to communication history
        message = f"Problem marked as resolved"
        if resolution_notes:
            message += f"\nResolution Notes: {resolution_notes}"
        
        self.add_communication(
            message=message,
            user=resolved_by,
            new_status='RESOLVED'
        )
        
        self.save()
    
    def update_status(self, new_status, notes="", updated_by=None):
        """Update problem status with tracking"""
        old_status = self.status
        self.status = new_status
        
        message = f"Status changed from {old_status} to {new_status}"
        if notes:
            message += f"\nNotes: {notes}"
        
        self.add_communication(
            message=message,
            user=updated_by,
            new_status=new_status
        )
        
        self.save()
    
    def assign_to(self, user, assigned_by=None):
        """Assign problem to user"""
        old_assignee = self.assigned_to
        self.assigned_to = user
        
        if old_assignee:
            message = f"Reassigned from {old_assignee.get_full_name()} to {user.get_full_name()}"
        else:
            message = f"Assigned to {user.get_full_name()}"
        
        self.add_communication(
            message=message,
            user=assigned_by
        )
        
        self.save()
    
    def get_recent_communications(self, limit=10):
        """Get recent communications"""
        if not self.communication_history:
            return []
        return self.communication_history[-limit:]
    
    def get_external_communications(self):
        """Get only external-facing communications"""
        if not self.communication_history:
            return []
        return [comm for comm in self.communication_history if not comm.get('is_internal', False)]
    
    def is_overdue(self):
        """Check if problem is overdue"""
        if self.due_date and self.status not in ['RESOLVED', 'CANCELLED']:
            return timezone.now().date() > self.due_date
        return False