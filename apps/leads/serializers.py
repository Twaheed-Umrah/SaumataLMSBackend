from rest_framework import serializers
from .models import Lead, LeadActivity, FollowUp, PulledLead
from apps.accounts.serializers import UserSerializer
from utils.constants import LeadStatus, LeadType, UserRole
from django.contrib.auth import get_user_model
User = get_user_model()

class LeadActivitySerializer(serializers.ModelSerializer):
    """
    Serializer for Lead Activity
    """
    user_name = serializers.CharField(source='user.get_full_name', read_only=True)
    
    class Meta:
        model = LeadActivity
        fields = [
            'id', 'lead', 'user', 'user_name', 'activity_type',
            'description', 'old_status', 'new_status', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class FollowUpSerializer(serializers.ModelSerializer):
    """
    Serializer for Follow Up
    """
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    lead_name = serializers.CharField(source='lead.name', read_only=True)
    
    class Meta:
        model = FollowUp
        fields = [
            'id', 'lead', 'lead_name', 'assigned_to', 'assigned_to_name',
            'scheduled_date', 'notes', 'completed', 'completed_at',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class LeadSerializer(serializers.ModelSerializer):
    """
    Serializer for Lead model
    """
    lead_type_display = serializers.CharField(source='get_lead_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    uploaded_by_name = serializers.CharField(source='uploaded_by.get_full_name', read_only=True)
    converted_by_name = serializers.CharField(source='converted_by.get_full_name', read_only=True)
    
    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'email', 'phone', 'company', 'city', 'state',
            'lead_type', 'lead_type_display', 'status', 'status_display',
            'assigned_to', 'assigned_to_name', 'uploaded_by', 'uploaded_by_name',
            'converted_by', 'converted_by_name', 'converted_at', 'original_type',
            'notes', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'converted_by', 'converted_at', 'created_at', 'updated_at']


class LeadDetailSerializer(serializers.ModelSerializer):
    """
    Detailed serializer for Lead with activities and follow-ups
    """
    lead_type_display = serializers.CharField(source='get_lead_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assigned_to_detail = UserSerializer(source='assigned_to', read_only=True)
    uploaded_by_detail = UserSerializer(source='uploaded_by', read_only=True)
    converted_by_detail = UserSerializer(source='converted_by', read_only=True)
    activities = LeadActivitySerializer(many=True, read_only=True)
    followups = FollowUpSerializer(many=True, read_only=True)
    
    class Meta:
        model = Lead
        fields = [
            'id', 'name', 'email', 'phone', 'company', 'city', 'state',
            'lead_type', 'lead_type_display', 'status', 'status_display',
            'assigned_to', 'assigned_to_detail', 'uploaded_by', 'uploaded_by_detail',
            'converted_by', 'converted_by_detail', 'converted_at', 'original_type',
            'notes', 'activities', 'followups', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'uploaded_by', 'converted_by', 'converted_at', 'created_at', 'updated_at']


class LeadCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating leads
    """
    class Meta:
        model = Lead
        fields = [
            'name', 'email', 'phone', 'company', 'city', 'state',
            'lead_type', 'status', 'assigned_to', 'notes'
        ]


class LeadUpdateSerializer(serializers.ModelSerializer):
    """
    Serializer for updating leads
    """
    class Meta:
        model = Lead
        fields = [
            'name', 'email', 'phone', 'company', 'city', 'state',
            'status', 'notes'
        ]


class LeadConversionSerializer(serializers.Serializer):
    new_type = serializers.ChoiceField(choices=['FRANCHISE', 'PACKAGE'])
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=False 
    )
    notes = serializers.CharField(required=False, allow_blank=True)


class LeadUploadSerializer(serializers.Serializer):
    """
    Serializer for bulk lead upload
    """
    file = serializers.FileField()
    lead_type = serializers.ChoiceField(choices=['FRANCHISE', 'PACKAGE'])

# In serializers.py, add this serializer
class LeadManualUploadSerializer(serializers.Serializer):
    """
    Serializer for manual lead upload with caller assignment
    """
    file = serializers.FileField()
    lead_type = serializers.ChoiceField(choices=['FRANCHISE', 'PACKAGE'])
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.all(),
        required=True
    )
    
    def validate(self, data):
        user = data['assigned_to']
        lead_type = data['lead_type']
        
        # Check if user is active
        if not user.is_active:
            raise serializers.ValidationError("Cannot assign to inactive user")
        
        # Check if user role matches lead type
        if lead_type == 'FRANCHISE' and user.role != UserRole.FRANCHISE_CALLER:
            raise serializers.ValidationError(
                "Franchise leads can only be assigned to franchise callers"
            )
        
        if lead_type == 'PACKAGE' and user.role != UserRole.PACKAGE_CALLER:
            raise serializers.ValidationError(
                "Package leads can only be assigned to package callers"
            )
        
        return data
    

# Add to serializers.py

class PullLeadByIdsSerializer(serializers.Serializer):
    """
    Pull specific leads by their IDs
    """
    lead_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=500
    )
    pull_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500
    )


class PullLeadByFiltersSerializer(serializers.Serializer):
    """
    Pull leads by various filters
    """
    # Caller filter (can use one or both)
    caller_id = serializers.IntegerField(required=False)
    caller_ids = serializers.ListField(
        child=serializers.IntegerField(),
        required=False,
        allow_empty=True
    )
    
    # Date filters
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    
    # Lead properties
    lead_type = serializers.ChoiceField(
        choices=LeadType.CHOICES,
        required=False
    )
    status = serializers.ChoiceField(
        choices=LeadStatus.CHOICES,
        required=False
    )
    statuses = serializers.ListField(
        child=serializers.ChoiceField(choices=LeadStatus.CHOICES),
        required=False,
        allow_empty=True
    )
    
    # Pull options
    pull_reason = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=500
    )
    limit = serializers.IntegerField(
        min_value=1,
        max_value=1000,
        default=300,
        required=False
    )
    
    def validate(self, data):
        """
        Validate that at least one filter is provided
        """
        filters_provided = any([
            'caller_id' in data,
            'caller_ids' in data and data['caller_ids'],
            'from_date' in data,
            'to_date' in data,
            'status' in data,
            'statuses' in data and data['statuses'],
            'lead_type' in data,
        ])
        
        if not filters_provided:
            raise serializers.ValidationError(
                "At least one filter criteria must be provided"
            )
        
        return data


class PulledLeadSerializer(serializers.ModelSerializer):
    """
    Serializer for PulledLead model
    """
    pulled_by_name = serializers.CharField(source='pulled_by.get_full_name', read_only=True)
    pulled_from_name = serializers.CharField(source='pulled_from.get_full_name', read_only=True)
    original_lead_type_display = serializers.CharField(source='get_original_lead_type_display', read_only=True)
    original_status_display = serializers.CharField(source='get_original_status_display', read_only=True)
    
    class Meta:
        model = PulledLead
        fields = [
            'id', 'original_lead_id', 'name', 'email', 'phone', 'company', 
            'city', 'state', 'notes', 'original_lead_type', 'original_lead_type_display',
            'original_status', 'original_status_display', 'pulled_by', 'pulled_by_name', 
            'pulled_from', 'pulled_from_name', 'pull_reason', 'filter_criteria',
            'exported', 'exported_at', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id','original_lead_id', 'pulled_by', 'pulled_from', 'created_at', 'updated_at',
            'exported', 'exported_at', 'filter_criteria'
        ]


class PulledLeadExportSerializer(serializers.ModelSerializer):
    """
    Serializer for exporting pulled leads (matches upload format)
    """
    class Meta:
        model = PulledLead
        fields = ['name', 'email', 'phone', 'company', 'city', 'state', 'notes']


class PulledLeadsForUploadSerializer(serializers.Serializer):
    """
    Serializer for preparing pulled leads for upload
    """
    pulled_lead_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1
    )


class TransferPulledLeadsSerializer(serializers.Serializer):
    """
    Serializer for transferring selected pulled leads
    """
    pulled_lead_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1,
        max_length=500,
        required=False,
        help_text="Specific PulledLead IDs to transfer"
    )
    
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            is_active=True,
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER]
        ),
        required=True
    )
    
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )
    
    def validate(self, data):
        # Either pulled_lead_ids OR filters must be provided
        if 'pulled_lead_ids' not in data:
            raise serializers.ValidationError(
                "Please provide pulled_lead_ids for transfer"
            )
        
        return data


class TransferByFiltersSerializer(serializers.Serializer):
    """
    Serializer for transferring pulled leads using filters
    """
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            is_active=True,
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER]
        ),
        required=True
    )
    
    # Date filters
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    
    # Lead properties
    status = serializers.ChoiceField(
        choices=LeadStatus.CHOICES,
        required=False
    )
    
    lead_type = serializers.ChoiceField(
        choices=LeadType.CHOICES,
        required=False
    )
    
    exported = serializers.BooleanField(required=False)
    
    # Limit
    limit = serializers.IntegerField(
        min_value=1,
        max_value=1000,
        default=100,
        required=False
    )
    
    notes = serializers.CharField(
        required=False,
        allow_blank=True,
        max_length=1000
    )
    
    def validate(self, data):
        # At least one filter must be provided
        if not any([
            'from_date' in data,
            'to_date' in data,
            'status' in data,
            'lead_type' in data,
            'exported' in data
        ]):
            raise serializers.ValidationError(
                "At least one filter criteria must be provided"
            )
        
        return data


class TransferPreviewSerializer(serializers.Serializer):
    """
    Serializer for previewing transfer by filters
    """
    from_date = serializers.DateField(required=False)
    to_date = serializers.DateField(required=False)
    status = serializers.ChoiceField(
        choices=LeadStatus.CHOICES,
        required=False
    )
    lead_type = serializers.ChoiceField(
        choices=LeadType.CHOICES,
        required=False
    )
    exported = serializers.BooleanField(required=False)
    limit = serializers.IntegerField(
        min_value=1,
        max_value=500,
        default=50,
        required=False
    )
    
    def validate(self, data):
        if not any([
            'from_date' in data,
            'to_date' in data,
            'status' in data,
            'lead_type' in data,
            'exported' in data
        ]):
            raise serializers.ValidationError(
                "At least one filter criteria must be provided"
            )
        return data
    

# In serializers.py, add this after LeadManualUploadSerializer

class LeadCreateManualSerializer(serializers.Serializer):
    """
    Serializer for manual single lead creation
    """
    name = serializers.CharField(max_length=255, required=True)
    email = serializers.EmailField(required=False, allow_blank=True)
    phone = serializers.CharField(max_length=15, required=True)
    city = serializers.CharField(max_length=100, required=False, allow_blank=True)
    state = serializers.CharField(max_length=100, required=False, allow_blank=True)
    lead_type = serializers.ChoiceField(choices=LeadType.CHOICES, required=True)
    status = serializers.ChoiceField(
        choices=LeadStatus.CHOICES, 
        required=False, 
        default=LeadStatus.NEW
    )
    assigned_to = serializers.PrimaryKeyRelatedField(
        queryset=User.objects.filter(
            is_active=True,
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER]
        ),
        required=False,
        allow_null=True
    )
    notes = serializers.CharField( required=False,
    allow_blank=True,
    allow_null=True)
    
    def validate(self, data):
        # Validate phone number
        phone = data.get('phone', '')
        if not phone:
            raise serializers.ValidationError("Phone number is required")
        
        # Clean and validate phone
        phone = ''.join(filter(str.isdigit, str(phone)))
        if phone.startswith('91') and len(phone) == 12:
            phone = phone[2:]
        elif len(phone) > 10:
            phone = phone[-10:]
        
        # Validate Indian mobile number
        if len(phone) != 10 or not phone.startswith(('6', '7', '8', '9')):
            raise serializers.ValidationError("Invalid Indian mobile number")
        
        data['phone'] = phone
        
        # Check if phone already exists
        if Lead.objects.filter(phone=phone).exists():
            raise serializers.ValidationError("Lead with this phone number already exists")
        
        # Validate assignment if provided
        assigned_to = data.get('assigned_to')
        lead_type = data.get('lead_type')
        
        if assigned_to:
            # Check if user role matches lead type
            if lead_type == 'FRANCHISE' and assigned_to.role != UserRole.FRANCHISE_CALLER:
                raise serializers.ValidationError(
                    "Franchise leads can only be assigned to franchise callers"
                )
            
            if lead_type == 'PACKAGE' and assigned_to.role != UserRole.PACKAGE_CALLER:
                raise serializers.ValidationError(
                    "Package leads can only be assigned to package callers"
                )
            
            # Check if caller is present
            if not assigned_to.is_present:
                raise serializers.ValidationError(
                    f"Caller {assigned_to.get_full_name()} is not marked as present"
                )
        
        return data