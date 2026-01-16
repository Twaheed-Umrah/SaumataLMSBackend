from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import ProblemReport
from django.utils import timezone

User = get_user_model()

class CommunicationSerializer(serializers.Serializer):
    """Serializer for communication history entries"""
    timestamp = serializers.DateTimeField()
    message = serializers.CharField()
    user_id = serializers.IntegerField(allow_null=True)
    user_name = serializers.CharField()
    is_internal = serializers.BooleanField()
    new_status = serializers.CharField(allow_null=True, required=False)


class ProblemReportSerializer(serializers.ModelSerializer):
    """
    Serializer for Problem Report
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    problem_type_display = serializers.CharField(source='get_problem_type_display', read_only=True)
    
    assigned_to_name = serializers.SerializerMethodField()
    reported_by_name = serializers.SerializerMethodField()
    
    # Communication history - FIXED
    recent_communications = serializers.SerializerMethodField()
    external_communications = serializers.SerializerMethodField()
    all_communications = serializers.SerializerMethodField()  # Changed to SerializerMethodField
    
    # Calculated fields
    resolution_time_hours = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    days_open = serializers.SerializerMethodField()
    
    class Meta:
        model = ProblemReport
        fields = [
            'id', 'title', 'description', 'problem_type', 'problem_type_display',
            'priority', 'priority_display', 'status', 'status_display',
            'customer_name', 'customer_email', 'customer_phone',
            'tour_package', 'travel_date',
            'assigned_to', 'assigned_to_name', 'reported_by', 'reported_by_name',
            'reported_date', 'due_date', 'resolved_date',
            'resolution_notes', 'resolution_time_minutes', 'resolution_time_hours',
            'is_resolved', 'is_overdue', 'days_open',
            'recent_communications', 'external_communications', 'all_communications',
            'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'is_resolved', 'resolved_date', 'resolution_time_minutes',
            'created_at', 'updated_at', 'communication_history'
        ]
    
    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to else None
    
    def get_reported_by_name(self, obj):
        return obj.reported_by.get_full_name() if obj.reported_by else None
    
    def get_resolution_time_hours(self, obj):
        """Convert resolution time to hours"""
        if obj.resolution_time_minutes:
            return round(obj.resolution_time_minutes / 60, 2)
        return None
    
    def get_is_overdue(self, obj):
        """Check if problem is overdue"""
        return obj.is_overdue()
    
    def get_days_open(self, obj):
        """Get number of days problem has been open"""
        if obj.is_resolved and obj.resolved_date:
            return (obj.resolved_date.date() - obj.reported_date.date()).days
        return (timezone.now().date() - obj.reported_date.date()).days
    
    def get_recent_communications(self, obj):
        """Get recent communications"""
        comms = obj.get_recent_communications()
        if not comms:
            return []
        
        # Parse timestamp strings to datetime objects
        for comm in comms:
            if isinstance(comm.get('timestamp'), str):
                try:
                    comm['timestamp'] = timezone.datetime.fromisoformat(comm['timestamp'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If parsing fails, keep original
                    pass
        
        return CommunicationSerializer(comms, many=True).data
    
    def get_external_communications(self, obj):
        """Get external communications"""
        comms = obj.get_external_communications()
        if not comms:
            return []
        
        # Parse timestamp strings to datetime objects
        for comm in comms:
            if isinstance(comm.get('timestamp'), str):
                try:
                    comm['timestamp'] = timezone.datetime.fromisoformat(comm['timestamp'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If parsing fails, keep original
                    pass
        
        return CommunicationSerializer(comms, many=True).data
    
    def get_all_communications(self, obj):
        """Get all communications"""
        comms = obj.communication_history or []
        if not comms:
            return []
        
        # Parse timestamp strings to datetime objects
        for comm in comms:
            if isinstance(comm.get('timestamp'), str):
                try:
                    comm['timestamp'] = timezone.datetime.fromisoformat(comm['timestamp'].replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If parsing fails, keep original
                    pass
        
        return CommunicationSerializer(comms, many=True).data
    
    def create(self, validated_data):
        """Create problem report with current user as reporter"""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['reported_by'] = request.user
        
        problem = super().create(validated_data)
        
        # Add initial communication
        problem.add_communication(
            message=f"Problem reported: {problem.title}\nDescription: {problem.description}",
            user=problem.reported_by,
            new_status=problem.status
        )
        
        return problem

class ProblemReportListSerializer(serializers.ModelSerializer):
    """
    Simplified serializer for Problem Report listing
    """
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    priority_display = serializers.CharField(source='get_priority_display', read_only=True)
    problem_type_display = serializers.CharField(source='get_problem_type_display', read_only=True)
    assigned_to_name = serializers.SerializerMethodField()
    is_overdue = serializers.SerializerMethodField()
    communications_count = serializers.SerializerMethodField()
    
    class Meta:
        model = ProblemReport
        fields = [
            'id', 'title', 'problem_type', 'problem_type_display',
            'priority', 'priority_display','description', 'status', 'status_display',
            'customer_name', 'tour_package','customer_phone','customer_email',
            'assigned_to_name', 'reported_date', 'due_date',
            'is_resolved', 'is_overdue', 'communications_count'
        ]
    
    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to else 'Unassigned'
    
    def get_is_overdue(self, obj):
        return obj.is_overdue()
    
    def get_communications_count(self, obj):
        return len(obj.communication_history) if obj.communication_history else 0


class ProblemUpdateSerializer(serializers.Serializer):
    """
    Serializer for updating problem
    """
    status = serializers.ChoiceField(
        choices=ProblemReport.PROBLEM_STATUS,
        required=False
    )
    priority = serializers.ChoiceField(
        choices=ProblemReport.PRIORITY_LEVELS,
        required=False
    )
    assigned_to = serializers.IntegerField(required=False, allow_null=True)
    resolution_notes = serializers.CharField(required=False, allow_blank=True)
    due_date = serializers.DateField(required=False, allow_null=True)
    
    # Communication fields
    message = serializers.CharField(required=False, allow_blank=True)
    is_internal = serializers.BooleanField(default=False)


class AddCommunicationSerializer(serializers.Serializer):
    """
    Serializer for adding communication
    """
    message = serializers.CharField(required=True)
    is_internal = serializers.BooleanField(default=False)
    new_status = serializers.ChoiceField(
        choices=ProblemReport.PROBLEM_STATUS,
        required=False,
        allow_null=True
    )


class ProblemBulkUpdateSerializer(serializers.Serializer):
    """
    Serializer for bulk updating problems
    """
    problem_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=True
    )
    status = serializers.ChoiceField(
        choices=ProblemReport.PROBLEM_STATUS,
        required=False
    )
    assigned_to = serializers.IntegerField(
        required=False,
        allow_null=True
    )
    priority = serializers.ChoiceField(
        choices=ProblemReport.PRIORITY_LEVELS,
        required=False
    )


class ProblemStatsSerializer(serializers.Serializer):
    """
    Serializer for problem statistics
    """
    total = serializers.IntegerField()
    by_status = serializers.DictField()
    by_priority = serializers.DictField()
    by_type = serializers.DictField()
    avg_resolution_time = serializers.FloatField()
    unresolved_overdue = serializers.IntegerField()
    today_count = serializers.IntegerField()
    week_count = serializers.IntegerField()
    month_count = serializers.IntegerField()