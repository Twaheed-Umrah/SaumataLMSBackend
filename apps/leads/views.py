import json
from datetime import datetime, time

from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework.response import Response
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from apps.accounts.models import User
from django.db.models import Q
from .models import Lead, FollowUp,PulledLead
from .serializers import (
    LeadSerializer, LeadDetailSerializer, LeadCreateSerializer,
    LeadUpdateSerializer, LeadConversionSerializer, LeadUploadSerializer,
    LeadActivitySerializer, FollowUpSerializer,PullLeadByIdsSerializer,
    PullLeadByFiltersSerializer,
    PulledLeadSerializer,
    PulledLeadsForUploadSerializer
)
from django.utils.dateparse import parse_date
from django.http import HttpResponse
from .services import (
    LeadDistributionService,
    LeadConversionService,
    LeadActivityService,
     LeadPullService
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
    

# In apps/leads/views.py (add these new views)
from rest_framework import status
from django.shortcuts import get_object_or_404


class CallerPresenceManagementAPIView(APIView):
    """
    API for team leaders/super admins to manage caller presence status
    """
    permission_classes = [IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def patch(self, request, caller_id=None):
        """
        Update a specific caller's presence status
        PATCH /api/leads/callers/<id>/presence/
        {
            "is_present": false
        }
        """
        try:
            caller = User.objects.get(id=caller_id, is_active=True)
            
            # Check if user is a caller
            if caller.role not in [UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER]:
                return error_response("User is not a caller", status_code=400)
            
            # Update is_present status
            is_present = request.data.get('is_present')
            if is_present is None:
                return error_response("is_present field is required", status_code=400)
            
            old_status = caller.is_present
            caller.is_present = bool(is_present)
            caller.save()
            
            action = "marked as present" if caller.is_present else "marked as not present"
            message = f"{caller.get_full_name()} has been {action}"
            
            if old_status != caller.is_present:
                # Log this action (optional)
                print(f"Caller {caller.id} presence changed from {old_status} to {caller.is_present} by {request.user.email}")
            
            return success_response(
                {
                    'id': caller.id,
                    'name': caller.get_full_name(),
                    'email': caller.email,
                    'role': caller.role,
                    'is_present': caller.is_present,
                    'previous_status': old_status
                },
                message
            )
            
        except User.DoesNotExist:
            return error_response("Caller not found", status_code=404)


class BulkCallerPresenceAPIView(APIView):
    """
    API for bulk operations on caller presence status
    """
    permission_classes = [IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def post(self, request):
        """
        Bulk update caller presence status
        POST /api/leads/callers/bulk-presence/
        {
            "caller_ids": [1, 2, 3],
            "is_present": true/false
        }
        OR
        {
            "lead_type": "FRANCHISE",  # or "PACKAGE"
            "is_present": true/false,
            "all": true
        }
        """
        caller_ids = request.data.get('caller_ids', [])
        lead_type = request.data.get('lead_type', '').upper()
        is_present = request.data.get('is_present')
        all_callers = request.data.get('all', False)
        
        if is_present is None:
            return error_response("is_present field is required", status_code=400)
        
        is_present_bool = bool(is_present)
        
        # Get queryset based on input
        if all_callers and lead_type:
            # Validate lead type
            if lead_type not in [LeadType.FRANCHISE, LeadType.PACKAGE]:
                return error_response(
                    f"Invalid lead type. Must be '{LeadType.FRANCHISE}' or '{LeadType.PACKAGE}'", 
                    status_code=400
                )
            
            # Get role based on lead type
            if lead_type == LeadType.FRANCHISE:
                role = UserRole.FRANCHISE_CALLER
            else:
                role = UserRole.PACKAGE_CALLER
            
            # Get all active callers of this type
            callers = User.objects.filter(role=role, is_active=True)
            action = f"all {lead_type.lower()} callers"
            
        elif caller_ids:
            # Update specific callers
            callers = User.objects.filter(
                id__in=caller_ids,
                is_active=True,
                role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER]
            )
            action = f"{callers.count()} caller(s)"
            
        else:
            return error_response(
                "Either provide caller_ids or lead_type with all=true", 
                status_code=400
            )
        
        if not callers.exists():
            return error_response("No valid callers found to update", status_code=404)
        
        # Update in bulk
        updated_count = callers.update(is_present=is_present_bool)
        
        status_text = "present" if is_present_bool else "not present"
        return success_response(
            {
                'updated_count': updated_count,
                'is_present': is_present_bool,
                'lead_type': lead_type if all_callers else None,
                'action': 'bulk_update'
            },
            f"{updated_count} caller(s) marked as {status_text}"
        )
    
    def get(self, request):
        """
        Get summary of caller presence status by lead type
        GET /api/leads/callers/bulk-presence/?lead_type=FRANCHISE
        """
        lead_type = request.query_params.get('lead_type', '').upper()
        
        if not lead_type:
            return error_response("lead_type query parameter is required", status_code=400)
        
        if lead_type not in [LeadType.FRANCHISE, LeadType.PACKAGE]:
            return error_response(
                f"Invalid lead type. Must be '{LeadType.FRANCHISE}' or '{LeadType.PACKAGE}'", 
                status_code=400
            )
        
        # Get role based on lead type
        if lead_type == LeadType.FRANCHISE:
            role = UserRole.FRANCHISE_CALLER
        else:
            role = UserRole.PACKAGE_CALLER
        
        # Get presence statistics
        from django.db.models import Count, Case, When, Value, IntegerField
        
        stats = User.objects.filter(
            role=role,
            is_active=True
        ).aggregate(
            total=Count('id'),
            present=Count(Case(When(is_present=True, then=Value(1)), output_field=IntegerField())),
            not_present=Count(Case(When(is_present=False, then=Value(1)), output_field=IntegerField()))
        )
        
        # Get list of callers
        callers = User.objects.filter(role=role, is_active=True).values(
            'id', 'first_name', 'last_name', 'email', 'is_present'
        ).order_by('is_present', 'first_name')
        
        return success_response(
            {
                'lead_type': lead_type,
                'statistics': stats,
                'callers': list(callers)
            },
            f"Presence status for {lead_type} callers"
        )
    

class LeadPullByIDsView(APIView):
    """
    API for pulling leads by specific IDs - MOVES leads
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def post(self, request):
        """
        Pull specific leads by their IDs - MOVES them to PulledLead table
        """
        serializer = PullLeadByIdsSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
        
        pulled_leads, failed_leads, deleted_leads = LeadPullService.pull_leads_by_ids(
            lead_ids=serializer.validated_data['lead_ids'],
            pulled_by=request.user,
            pull_reason=serializer.validated_data.get('pull_reason', '')
        )
        
        response_data = {
            'successful': len(pulled_leads),
            'failed': len(failed_leads),
            'deleted_from_leads_table': len(deleted_leads),
            'total_requested': len(serializer.validated_data['lead_ids']),
            'action': 'MOVED (not copied)'
        }
        
        if failed_leads:
            response_data['failed_details'] = failed_leads[:10]
        
        if deleted_leads:
            response_data['deleted_leads_ids'] = [lead['id'] for lead in deleted_leads]
        
        message = f"Successfully MOVED {len(pulled_leads)} leads from Lead table to PulledLead table"
        if failed_leads:
            message += f", {len(failed_leads)} failed"
        
        return success_response(response_data, message)


class LeadPullByFiltersView(APIView):
    """
    API for pulling leads by filters - MOVES leads
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def post(self, request):
        """
        Pull leads using advanced filters - MOVES them to PulledLead table
        """
        serializer = PullLeadByFiltersSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
        
        pulled_leads, failed_leads, deleted_leads = LeadPullService.pull_leads_by_filters(
            filters=serializer.validated_data,
            pulled_by=request.user
        )
        
        response_data = {
            'successful': len(pulled_leads),
            'failed': len(failed_leads),
            'deleted_from_leads_table': len(deleted_leads),
            'filters_applied': serializer.validated_data,
            'action': 'MOVED (not copied)'
        }
        
        if deleted_leads:
            response_data['deleted_leads_count'] = len(deleted_leads)
        
        message = f"Successfully MOVED {len(pulled_leads)} leads from Lead table to PulledLead table using filters"
        if failed_leads:
            message += f", {len(failed_leads)} failed"
        
        return success_response(response_data, message)

class PulledLeadsListView(APIView):
    """
    API for viewing pulled leads with filters
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def get(self, request):
        """
        Get list of pulled leads with various filters
        GET /api/leads/pulled/
        
        Query Parameters:
        - caller_id: Filter by caller
        - status: Filter by original status (RNR, CONTACTED, etc.)
        - lead_type: Filter by lead type
        - exported: true/false (filter by export status)
        - from_date: Filter from date
        - to_date: Filter to date
        - search: Search in name, phone, email
        - page: Page number
        - page_size: Items per page
        """
        queryset = LeadPullService.get_pulled_leads_queryset(request.user)
        
        # Apply filters
        caller_id = request.query_params.get('caller_id')
        if caller_id:
            queryset = queryset.filter(pulled_from__id=caller_id)
        
        status = request.query_params.get('status')
        if status:
            queryset = queryset.filter(original_status=status)
        
        lead_type = request.query_params.get('lead_type')
        if lead_type:
            queryset = queryset.filter(original_lead_type=lead_type)
        
        exported = request.query_params.get('exported')
        if exported is not None:
            queryset = queryset.filter(exported=exported.lower() == 'true')
        
        # Date filters
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        
        if from_date:
            from_date_parsed = parse_date(from_date)
            if from_date_parsed:
                queryset = queryset.filter(created_at__date__gte=from_date_parsed)
        
        if to_date:
            to_date_parsed = parse_date(to_date)
            if to_date_parsed:
                queryset = queryset.filter(created_at__date__lte=to_date_parsed)
        
        # Search
        search = request.query_params.get('search')
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(phone__icontains=search) |
                Q(email__icontains=search) |
                Q(company__icontains=search)
            )
        
        # Ordering
        order_by = request.query_params.get('order_by', '-created_at')
        if order_by.lstrip('-') in ['name', 'phone', 'created_at', 'original_status']:
            queryset = queryset.order_by(order_by)
        
        # Pagination
        try:
            page_size = int(request.query_params.get('page_size', 20))
            page = int(request.query_params.get('page', 1))
        except ValueError:
            page_size = 20
            page = 1
        
        start = (page - 1) * page_size
        end = start + page_size
        
        total_count = queryset.count()
        leads = queryset[start:end]
        
        serializer = PulledLeadSerializer(leads, many=True)
        
        return success_response({
            'results': serializer.data,
            'count': total_count,
            'page': page,
            'page_size': page_size,
            'total_pages': (total_count + page_size - 1) // page_size
        }, "Pulled leads retrieved successfully")


class PulledLeadsExportView(APIView):
    """
    Export Pulled Leads to Excel

    Rules:
    - If NO data → return JSON message (NO Excel)
    - If data exists → return Excel
    - exported=true / false → always export if data exists
    - exported_at updated only when Excel is generated
    """

    def get(self, request, *args, **kwargs):
        filters = {}
    
        filters["lead_type"] = request.query_params.get("lead_type")
    
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")
    
        if from_date:
            filters["from_date"] = parse_date(from_date)
        if to_date:
            filters["to_date"] = parse_date(to_date)
    
        caller_id = request.query_params.get("caller_id")
        if caller_id:
            filters["caller_id"] = caller_id
    
        pulled_lead_ids = request.query_params.getlist("pulled_lead_ids")
    
        excel_file, error = LeadPullService.export_pulled_leads_to_excel(
            pulled_lead_ids=pulled_lead_ids or None,
            filters=filters
        )
    
        if error:
            return Response(
                {"success": False, "message": error},
                status=400
            )
    
        response = HttpResponse(
            excel_file.getvalue(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
        response["Content-Disposition"] = 'attachment; filename="pulled_leads.xlsx"'
    
        return response



class PulledLeadsStatisticsView(APIView):
    """
    API for getting statistics about pulled leads
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def get(self, request):
        """
        Get statistics about pulled leads
        GET /api/leads/pulled/statistics/
        
        Query Parameters:
        - caller_id: Filter statistics by caller
        - from_date: Filter from date
        - to_date: Filter to date
        - lead_type: Filter by lead type
        """
        # Get base statistics
        stats = LeadPullService.get_lead_pull_statistics(request.user)
        
        # Apply additional filters if provided
        caller_id = request.query_params.get('caller_id')
        from_date = request.query_params.get('from_date')
        to_date = request.query_params.get('to_date')
        lead_type = request.query_params.get('lead_type')
        
        if any([caller_id, from_date, to_date, lead_type]):
            # Get filtered queryset
            queryset = LeadPullService.get_pulled_leads_queryset(request.user)
            
            if caller_id:
                queryset = queryset.filter(pulled_from__id=caller_id)
            
            if from_date:
                from_date_parsed = parse_date(from_date)
                if from_date_parsed:
                    queryset = queryset.filter(created_at__date__gte=from_date_parsed)
            
            if to_date:
                to_date_parsed = parse_date(to_date)
                if to_date_parsed:
                    queryset = queryset.filter(created_at__date__lte=to_date_parsed)
            
            if lead_type:
                queryset = queryset.filter(original_lead_type=lead_type)
            
            # Calculate filtered statistics
            from django.db.models import Count, Q
            
            filtered_stats = queryset.aggregate(
                total_pulled=Count('id'),
                exported=Count('id', filter=Q(exported=True)),
                not_exported=Count('id', filter=Q(exported=False)),
                
            )
            
            # Group by status
            status_stats = list(
                queryset.values('original_status')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
            
            # Group by lead type
            type_stats = list(
                queryset.values('original_lead_type')
                .annotate(count=Count('id'))
                .order_by('-count')
            )
            
            stats['filtered'] = {
                'overall': filtered_stats,
                'by_status': status_stats,
                'by_lead_type': type_stats,
                'filters_applied': {
                    'caller_id': caller_id,
                    'from_date': from_date,
                    'to_date': to_date,
                    'lead_type': lead_type
                }
            }
        
        return success_response(stats, "Pulled leads statistics retrieved")


class PulledLeadsPrepareUploadView(APIView):
    """
    API for preparing pulled leads for upload
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def post(self, request):
        """
        Get pulled leads data in upload format
        POST /api/leads/pulled/prepare-upload/
        
        Returns the actual lead data that can be used to create an Excel file
        for upload using the existing upload_manual API
        """
        serializer = PulledLeadsForUploadSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
        
        upload_data = LeadPullService.get_pulled_leads_for_upload(
            serializer.validated_data['pulled_lead_ids']
        )
        
        return success_response(
            {
                'leads': upload_data,
                'count': len(upload_data),
                'format': 'upload_ready'
            },
            f"Prepared {len(upload_data)} leads for upload"
        )


class BulkLeadPullPreviewView(APIView):
    """
    API for previewing which leads will be pulled
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def post(self, request):
        """
        Preview leads that match filter criteria before pulling
        POST /api/leads/pull/preview/
        
        Returns leads that match the criteria without actually pulling them
        """
        serializer = PullLeadByFiltersSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
        
        filters = serializer.validated_data
        
        # Build query similar to service but without pulling
        query = Q()
        
        # Filter by caller(s)
        if 'caller_id' in filters:
            query &= Q(assigned_to__id=filters['caller_id'])
        elif 'caller_ids' in filters and filters['caller_ids']:
            query &= Q(assigned_to__id__in=filters['caller_ids'])
        
        # Filter by date range
        if 'from_date' in filters and filters['from_date']:
            from_datetime = timezone.make_aware(
                datetime.combine(filters['from_date'], time.min)
            )
            query &= Q(created_at__gte=from_datetime)
        
        if 'to_date' in filters and filters['to_date']:
            to_datetime = timezone.make_aware(
                datetime.combine(filters['to_date'], time.max)
            )
            query &= Q(created_at__lte=to_datetime)
        
        # Filter by lead type
        if 'lead_type' in filters and filters['lead_type']:
            query &= Q(lead_type=filters['lead_type'])
        
        # Filter by status
        if 'status' in filters and filters['status']:
            query &= Q(status=filters['status'])
        elif 'statuses' in filters and filters['statuses']:
            query &= Q(status__in=filters['statuses'])
        
        # Get leads
        limit = filters.get('limit', 300)
        leads = Lead.objects.filter(query).order_by('-created_at')[:limit]
        
        # Check for already pulled leads
        lead_data = []
        for lead in leads:
            already_pulled = PulledLead.objects.filter(
                phone=lead.phone,
                pulled_from=lead.assigned_to,
                exported=False
            ).exists()
            
            lead_data.append({
                'id': lead.id,
                'name': lead.name,
                'phone': lead.phone,
                'email': lead.email,
                'status': lead.status,
                'lead_type': lead.lead_type,
                'assigned_to': {
                    'id': lead.assigned_to.id if lead.assigned_to else None,
                    'name': lead.assigned_to.get_full_name() if lead.assigned_to else None
                },
                'created_at': lead.created_at,
                'already_pulled': already_pulled,
                'can_be_pulled': not already_pulled and lead.assigned_to is not None
            })
        
        return success_response(
            {
                'preview_leads': lead_data,
                'total_matched': len(leads),
                'can_be_pulled': sum(1 for l in lead_data if l['can_be_pulled']),
                'already_pulled': sum(1 for l in lead_data if l['already_pulled']),
                'filters_applied': filters
            },
            f"Preview: {len(leads)} leads match the criteria"
        )


class CallerLeadsSummaryView(APIView):
    """
    API for getting summary of leads by caller
    """
    permission_classes = [IsAuthenticated, IsTeamLeaderOrSuperAdminOrLeadDistributer]
    
    def get(self, request):
        """
        Get summary of leads by caller for easier pulling
        GET /api/leads/pull/caller-summary/
        
        Returns count of leads by status for each caller
        """
        from django.db.models import Count
        
        # Get all active callers
        franchise_callers = User.objects.filter(
            role=UserRole.FRANCHISE_CALLER,
            is_active=True
        )
        package_callers = User.objects.filter(
            role=UserRole.PACKAGE_CALLER,
            is_active=True
        )
        
        caller_summary = []
        
        # Process franchise callers
        for caller in franchise_callers:
            leads_summary = Lead.objects.filter(
                assigned_to=caller,
                lead_type=LeadType.FRANCHISE
            ).values('status').annotate(count=Count('id'))
            
            caller_summary.append({
                'id': caller.id,
                'name': caller.get_full_name(),
                'email': caller.email,
                'role': caller.role,
                'lead_type': LeadType.FRANCHISE,
                'status_summary': list(leads_summary),
                'total_leads': sum(item['count'] for item in leads_summary)
            })
        
        # Process package callers
        for caller in package_callers:
            leads_summary = Lead.objects.filter(
                assigned_to=caller,
                lead_type=LeadType.PACKAGE
            ).values('status').annotate(count=Count('id'))
            
            caller_summary.append({
                'id': caller.id,
                'name': caller.get_full_name(),
                'email': caller.email,
                'role': caller.role,
                'lead_type': LeadType.PACKAGE,
                'status_summary': list(leads_summary),
                'total_leads': sum(item['count'] for item in leads_summary)
            })
        
        # Sort by total leads descending
        caller_summary.sort(key=lambda x: x['total_leads'], reverse=True)
        
        return success_response(
            {
                'callers': caller_summary,
                'total_franchise_callers': franchise_callers.count(),
                'total_package_callers': package_callers.count()
            },
            "Caller leads summary retrieved"
        )