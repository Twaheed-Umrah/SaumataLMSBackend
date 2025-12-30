import json
from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated

from .models import Lead, FollowUp
from .serializers import (
    LeadSerializer, LeadDetailSerializer, LeadCreateSerializer,
    LeadUpdateSerializer, LeadConversionSerializer, LeadUploadSerializer,
    LeadActivitySerializer, FollowUpSerializer
)
from django.utils.dateparse import parse_date

from .services import (
    LeadDistributionService,
    LeadConversionService,
    LeadActivityService,
)
from utils.constants import UserRole, LeadType, LeadStatus
from utils.permissions import IsTeamLeaderOrSuperAdmin, IsCallerOrAbove,IsTeamLeaderOrSuperAdminOrLeadDistributer
from utils.response import success_response, error_response, created_response
from utils.excel import parse_excel_leads


class LeadViewSet(viewsets.ModelViewSet):
    """
    Production-ready Lead ViewSet
    """
    permission_classes = [IsAuthenticated]
    serializer_class = LeadSerializer

    filterset_fields = ['lead_type', 'status', 'assigned_to']
    search_fields = ['name', 'email', 'phone', 'company']
    ordering_fields = ['created_at', 'updated_at', 'name']

    # =========================
    # QUERYSET (ROLE BASED)
    # =========================
    def get_queryset(self):
        user = self.request.user
        qs = Lead.objects.all()

        if user.role in [UserRole.SUPER_ADMIN, UserRole.TEAM_LEADER, UserRole.LEAD_DISTRIBUTER,]:
            return qs

        if user.role == UserRole.FRANCHISE_CALLER:
            return qs.filter(
                assigned_to=user,
                lead_type=LeadType.FRANCHISE
            )

        if user.role == UserRole.PACKAGE_CALLER:
            return qs.filter(
                assigned_to=user,
                lead_type=LeadType.PACKAGE
            )

        return qs.none()

    # =========================
    # SERIALIZER SWITCH
    # =========================
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LeadDetailSerializer
        if self.action == 'create':
            return LeadCreateSerializer
        if self.action in ['update', 'partial_update']:
            return LeadUpdateSerializer
        return LeadSerializer

    # =========================
    # LIST (ACTIVE LEADS)
    # =========================
    def list(self, request):
        queryset = self.filter_queryset(self.get_queryset())
        queryset = queryset.exclude(status=LeadStatus.CONVERTED)

        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        date = request.query_params.get("date")
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if date:
            parsed = parse_date(date)
            if not parsed:
                return error_response("Invalid date format (YYYY-MM-DD)")
            start = datetime.combine(parsed, time.min)
            end = datetime.combine(parsed, time.max)
            queryset = queryset.filter(created_at__range=(start, end))

        elif from_date and to_date:
            f = parse_date(from_date)
            t = parse_date(to_date)
            if not f or not t:
                return error_response("Invalid date format (YYYY-MM-DD)")
            queryset = queryset.filter(created_at__date__range=(f, t))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, "Leads retrieved successfully")

    # =========================
    # CREATE LEAD
    # =========================
    def create(self, request):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        lead = serializer.save(uploaded_by=request.user)

        LeadActivityService.log_activity(
            lead=lead,
            user=request.user,
            activity_type="NOTE",
            description="Lead created"
        )

        return created_response(
            LeadSerializer(lead).data,
            "Lead created successfully"
        )

    # =========================
    # UPDATE LEAD
    # =========================
    def update(self, request, *args, **kwargs):
        lead = self.get_object()
        old_status = lead.status

        serializer = self.get_serializer(
            lead,
            data=request.data,
            partial=kwargs.get("partial", False)
        )

        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        lead = serializer.save()

        if "status" in request.data and old_status != lead.status:
            LeadActivityService.log_status_change(
                lead=lead,
                user=request.user,
                old_status=old_status,
                new_status=lead.status,
                notes=request.data.get("notes", "")
            )

        return success_response(
            LeadSerializer(lead).data,
            "Lead updated successfully"
        )

    # =========================
    # BULK UPLOAD (EXCEL)
    # =========================
    @action(detail=False, methods=["post"], permission_classes=[IsTeamLeaderOrSuperAdminOrLeadDistributer])
    def upload(self, request):
        serializer = LeadUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        file = serializer.validated_data["file"]
        lead_type = serializer.validated_data["lead_type"]

        column_mapping = request.data.get("mapping")
        if column_mapping:
            try:
                column_mapping = json.loads(column_mapping)
            except Exception:
                column_mapping = None

        leads_data, error = parse_excel_leads(file, column_mapping)
        if error:
            return error_response(error)

        if not leads_data:
            return error_response("No valid leads found")

        created, error = LeadDistributionService.distribute_leads(
            leads_data=leads_data,
            lead_type=lead_type,
            uploaded_by=request.user,
            column_mapping=column_mapping
        )

        if error:
            return error_response(error)

        return created_response(
            {
                "total": len(leads_data),
                "successful": len(created),
                "failed": len(leads_data) - len(created),
                "lead_type": lead_type,
            },
            f"{len(created)} leads uploaded successfully"
        )

    # =========================
    # CONVERT LEAD
    # =========================
    @action(detail=True, methods=["post"], permission_classes=[IsCallerOrAbove])
    def convert(self, request, pk=None):
        lead = self.get_object()

        serializer = LeadConversionSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        converted_lead, error = LeadConversionService.convert_lead(
            lead=lead,
            new_type=serializer.validated_data["new_type"],
            converted_by=request.user,
            notes=serializer.validated_data.get("notes", ""),
            assigned_to=serializer.validated_data.get("assigned_to"),
        )

        if error:
            return error_response(error)

        return success_response(
            LeadSerializer(converted_lead).data,
            "Lead converted successfully"
        )

    # =========================
    # ADD ACTIVITY
    # =========================
    @action(detail=True, methods=["post"])
    def add_activity(self, request, pk=None):
        lead = self.get_object()
        activity_type = request.data.get("activity_type", "NOTE")
        description = request.data.get("description")

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

    # =========================
    # MY LEADS
    # =========================
    @action(detail=False, methods=["get"])
    def my_leads(self, request):
        leads = Lead.objects.filter(
            assigned_to=request.user,
            converted_by__isnull=True,
            converted_at__isnull=True,
            original_type__isnull=True
        )

        status_param = request.query_params.get("status")
        if status_param:
            leads = leads.filter(status=status_param)

        date = request.query_params.get("date")
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if date:
            parsed = parse_date(date)
            if not parsed:
                return error_response("Invalid date format")
            leads = leads.filter(created_at__date=parsed)

        elif from_date and to_date:
            f = parse_date(from_date)
            t = parse_date(to_date)
            if not f or not t:
                return error_response("Invalid date format")
            leads = leads.filter(created_at__date__range=(f, t))

        page = self.paginate_queryset(leads)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(leads, many=True)
        return success_response(serializer.data, "My leads retrieved successfully")

    # =========================
    # CONVERTED LEADS
    # =========================
    @action(detail=False, methods=["get"])
    def converted(self, request):
        queryset = self.get_queryset().filter(
            converted_by__isnull=False,
            converted_at__isnull=False,
            original_type__isnull=False
        )

        date = request.query_params.get("date")
        if date:
            parsed = parse_date(date)
            if not parsed:
                return error_response("Invalid date format")
            queryset = queryset.filter(converted_at__date=parsed)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            serializer.data,
            "Converted leads retrieved successfully"
        )
    # In views.py, add this method to LeadViewSet class
    @action(detail=False, methods=['post'], permission_classes=[IsTeamLeaderOrSuperAdminOrLeadDistributer])
    def upload_manual(self, request):
        """
        Upload leads and assign to specific caller (manual assignment)
        """
        from .serializers import LeadManualUploadSerializer
        from .services import LeadManualUploadService
        
        serializer = LeadManualUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
        
        file = serializer.validated_data['file']
        lead_type = serializer.validated_data['lead_type']
        assigned_to = serializer.validated_data['assigned_to']
        
        # Optional column mapping
        column_mapping = request.data.get('mapping')
        if column_mapping:
            try:
                column_mapping = json.loads(column_mapping)
            except Exception:
                column_mapping = None
        
        # Upload and assign leads
        result, error = LeadManualUploadService.upload_and_assign(
            file=file,
            lead_type=lead_type,
            assigned_to=assigned_to,
            uploaded_by=request.user,
            column_mapping=column_mapping
        )
        
        if error:
            return error_response(error)
        
        # Prepare response data
        response_data = {
            'summary': {
                'total_rows': result['total_rows'],
                'successful': result['successful'],
                'failed': result['failed'],
                'lead_type': lead_type,
                'assigned_to': {
                    'id': assigned_to.id,
                    'name': assigned_to.get_full_name(),
                    'email': assigned_to.email
                }
            }
        }
        
        # Include failed leads details if any
        if result['failed'] > 0:
            response_data['failed_details'] = result['failed_leads'][:10]  # Limit to first 10 failures
        
        # Include success leads count by status
        if result['successful'] > 0:
            response_data['summary']['leads_created'] = len(result['created_leads'])
        
        return created_response(
            response_data,
            f"Successfully uploaded {result['successful']} leads and assigned to {assigned_to.get_full_name()}"
        )
    
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