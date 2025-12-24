import json
from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from django.db.models import Q
from django.utils import timezone
from .models import Lead, LeadActivity, FollowUp
from .serializers import (
    LeadSerializer, LeadDetailSerializer, LeadCreateSerializer,
    LeadUpdateSerializer, LeadConversionSerializer, LeadUploadSerializer,
    LeadActivitySerializer, FollowUpSerializer
)
from .services import (
    LeadDistributionService, LeadConversionService, LeadActivityService
)
from utils.constants import UserRole, LeadType, LeadStatus
from utils.permissions import IsTeamLeaderOrSuperAdmin, IsCallerOrAbove
from utils.response import success_response, error_response, created_response
from utils.excel import validate_excel_file, parse_excel_leads


class LeadViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Lead CRUD operations
    """
    queryset = Lead.objects.all()
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ['lead_type', 'status', 'assigned_to']
    search_fields = ['name', 'email', 'phone', 'company']
    ordering_fields = ['created_at', 'updated_at', 'name']
    
    def get_queryset(self):
       """
       Filter queryset based on user role
       Exclude converted leads from main lead list
       """
       user = self.request.user
   
       # 🔴 EXCLUDE converted leads globally
       queryset = Lead.objects.exclude(status=LeadStatus.CONVERTED)

       # Super Admin and Team Leader see all active leads
       if user.role in [UserRole.SUPER_ADMIN, UserRole.TEAM_LEADER]:
           return queryset
   
       # Franchise Caller
       if user.role == UserRole.FRANCHISE_CALLER:
           return queryset.filter(
               assigned_to=user,
               lead_type=LeadType.FRANCHISE
           )
   
       # Package Caller
       if user.role == UserRole.PACKAGE_CALLER:
           return queryset.filter(
               assigned_to=user,
               lead_type=LeadType.PACKAGE
           )
   
       return queryset.none()

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LeadDetailSerializer
        elif self.action == 'create':
            return LeadCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LeadUpdateSerializer
        return LeadSerializer
    
    def list(self, request):
        """List leads based on user role"""
        queryset = self.filter_queryset(self.get_queryset())
        
        # Additional filters
        status_filter = request.query_params.get('status')
        if status_filter:
            queryset = queryset.filter(status=status_filter)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, "Leads retrieved successfully")
    
    def create(self, request):
        """Create a new lead"""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            lead = serializer.save(uploaded_by=request.user)
            LeadActivityService.log_activity(
                lead=lead,
                user=request.user,
                activity_type='NOTE',
                description='Lead created'
            )
            return created_response(
                LeadSerializer(lead).data,
                "Lead created successfully"
            )
        return error_response("Validation failed", serializer.errors)
    
    def retrieve(self, request, pk=None):
        """Get lead details"""
        try:
            lead = self.get_object()
            serializer = self.get_serializer(lead)
            return success_response(serializer.data)
        except Lead.DoesNotExist:
            return error_response("Lead not found", status_code=status.HTTP_404_NOT_FOUND)
    
    def update(self, request, *args, **kwargs):
        lead = self.get_object()
        old_status = lead.status

        serializer = self.get_serializer(
            lead,
            data=request.data,
            partial=kwargs.get('partial', False)
        )
    
        if serializer.is_valid():
            lead = serializer.save()
    
            # Log status change
            if 'status' in request.data and old_status != lead.status:
                LeadActivityService.log_status_change(
                    lead=lead,
                    user=request.user,
                    old_status=old_status,
                    new_status=lead.status,
                    notes=request.data.get('notes', '')
                )
    
            return success_response(
                LeadSerializer(lead).data,
                "Lead updated successfully"
            )

        return error_response("Validation failed", serializer.errors)


    @action(detail=False, methods=['post'], permission_classes=[IsTeamLeaderOrSuperAdmin])
    def upload(self, request):
        """Bulk upload leads from Excel"""
        serializer = LeadUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
    
        file = serializer.validated_data['file']
        lead_type = serializer.validated_data['lead_type']
    
        # Get column mapping from request if provided
        column_mapping = request.data.get('mapping')
        if column_mapping:
            try:
                column_mapping = json.loads(column_mapping)
            except:
                column_mapping = None
    
        # Parse Excel with optional mapping
        leads_data, error_msg = parse_excel_leads(file, column_mapping)
    
        if error_msg:
            return error_response(error_msg)
    
        if not leads_data:
            return error_response("No valid leads found in the file")
    
        # Distribute leads
        created_leads, error_msg = LeadDistributionService.distribute_leads(
            leads_data, lead_type, request.user, column_mapping
        )
    
        if error_msg:
            return error_response(error_msg)
    
        if not created_leads:
            return error_response("No leads were created. Please check your file format.")
    
        return created_response(
            {
                'total_leads': len(created_leads),
                'lead_type': lead_type,
                'successful': len(created_leads),
                'failed': len(leads_data) - len(created_leads)
            },
            f"{len(created_leads)} leads uploaded and distributed successfully"
        )
    @action(detail=False, methods=['get'])
    def converted(self, request):
        """
        Show converted leads based on role
        """
        user = request.user

        # Base queryset: all converted leads
        leads = Lead.objects.filter(converted_at__isnull=False)
    
        # Caller-level restriction
        if user.role == UserRole.FRANCHISE_CALLER:
            leads = leads.filter(
                assigned_to=user,
                lead_type=LeadType.FRANCHISE
            )
    
        elif user.role == UserRole.PACKAGE_CALLER:
            leads = leads.filter(
                assigned_to=user,
                lead_type=LeadType.PACKAGE
            )
    
        # Team Leader & Super Admin:
        # no extra filters → see all converted leads
    
        serializer = self.get_serializer(leads, many=True)
        return success_response(serializer.data, "Converted leads retrieved successfully")

    
    @action(detail=False, methods=['get'])
    def my_leads(self, request):
        """Get leads assigned to current user"""
        user = request.user
        leads = Lead.objects.filter(
            assigned_to=user,
            status__in=[LeadStatus.NEW, LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP],
            converted_at__isnull=True
        )
        
        page = self.paginate_queryset(leads)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        serializer = self.get_serializer(leads, many=True)
        return success_response(serializer.data, "Your leads retrieved successfully")
    
    @action(detail=True, methods=['post'],permission_classes=[IsCallerOrAbove])
    def convert(self, request, pk=None):
        """
        Convert lead:
        - Package → Franchise
        - Franchise → Package
        """
        lead = self.get_object()
        serializer = LeadConversionSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        new_type = serializer.validated_data['new_type']
        assigned_to = serializer.validated_data.get('assigned_to')
        notes = serializer.validated_data.get('notes', '')

        converted_lead, error = LeadConversionService.convert_lead(
            lead=lead,
            new_type=new_type,
            converted_by=request.user,
            notes=notes,
            assigned_to=assigned_to
        )

        if error:
            return error_response(error)

        return success_response(
            LeadSerializer(converted_lead).data,
            "Lead converted successfully"
        )

    @action(detail=True, methods=['post'])
    def add_activity(self, request, pk=None):
        """Add activity to a lead"""
        try:
            lead = self.get_object()
            activity_type = request.data.get('activity_type', 'NOTE')
            description = request.data.get('description', '')
            
            if not description:
                return error_response("Description is required")
            
            activity = LeadActivityService.log_activity(
                lead=lead,
                user=request.user,
                activity_type=activity_type,
                description=description
            )
            
            return created_response(
                LeadActivitySerializer(activity).data,
                "Activity added successfully"
            )
        except Lead.DoesNotExist:
            return error_response("Lead not found", status_code=status.HTTP_404_NOT_FOUND)


class FollowUpViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Follow-up operations
    """
    queryset = FollowUp.objects.all()
    serializer_class = FollowUpSerializer
    permission_classes = [IsAuthenticated]
    
    def get_queryset(self):
        """Filter follow-ups based on user role"""
        user = self.request.user
        
        if user.role in [UserRole.SUPER_ADMIN, UserRole.TEAM_LEADER]:
            return FollowUp.objects.all()
        
        return FollowUp.objects.filter(assigned_to=user)
    
    def create(self, request):
        """Create a follow-up"""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            followup = serializer.save()
            return created_response(
                serializer.data,
                "Follow-up created successfully"
            )
        return error_response("Validation failed", serializer.errors)
    
    @action(detail=True, methods=['post'])
    def complete(self, request, pk=None):
        """Mark follow-up as completed"""
        try:
            followup = self.get_object()
            followup.completed = True
            followup.completed_at = timezone.now()
            followup.save()
            
            return success_response(
                self.get_serializer(followup).data,
                "Follow-up marked as completed"
            )
        except FollowUp.DoesNotExist:
            return error_response("Follow-up not found", status_code=status.HTTP_404_NOT_FOUND)
    
    @action(detail=False, methods=['get'])
    def pending(self, request):
        """Get pending follow-ups"""
        followups = self.get_queryset().filter(completed=False)
        serializer = self.get_serializer(followups, many=True)
        return success_response(serializer.data, "Pending follow-ups retrieved successfully")