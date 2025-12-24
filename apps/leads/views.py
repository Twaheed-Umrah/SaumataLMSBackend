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
from django.utils.dateparse import parse_date
from .services import (
    LeadDistributionService, LeadConversionService, LeadActivityService
)
from utils.constants import UserRole, LeadType, LeadStatus
from utils.permissions import IsTeamLeaderOrSuperAdmin, IsCallerOrAbove
from utils.response import success_response, error_response, created_response
from utils.excel import validate_excel_file, parse_excel_leads
from datetime import datetime, time
from django.utils.dateparse import parse_date
from rest_framework import viewsets, status



class LeadViewSet(viewsets.ModelViewSet):
    """
    Production-safe Lead ViewSet
    """
    serializer_class = LeadSerializer
    permission_classes = [IsAuthenticated]

    filterset_fields = ['lead_type', 'status', 'assigned_to']
    search_fields = ['name', 'email', 'phone', 'company']
    ordering_fields = ['created_at', 'updated_at', 'name']

    # -------------------------
    # BASE QUERYSET (NO FILTER)
    # -------------------------
    def get_queryset(self):
        """
        DO NOT apply business filters here.
        Only role-based access.
        """
        user = self.request.user
        qs = Lead.objects.all()

        if user.role in [UserRole.SUPER_ADMIN, UserRole.TEAM_LEADER]:
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

    # -------------------------
    # SERIALIZERS
    # -------------------------
    def get_serializer_class(self):
        if self.action == 'retrieve':
            return LeadDetailSerializer
        elif self.action == 'create':
            return LeadCreateSerializer
        elif self.action in ['update', 'partial_update']:
            return LeadUpdateSerializer
        return LeadSerializer

    # -------------------------
    # LIST (ACTIVE + FILTERS)
    # -------------------------
    def list(self, request):
        """
        Active leads list (non-converted)
        Supports: status + date
        """
        queryset = self.filter_queryset(self.get_queryset())

        # 🔴 Active leads ONLY
        queryset = queryset.exclude(status=LeadStatus.CONVERTED)

        # Status filter
        status_param = request.query_params.get("status")
        if status_param:
            queryset = queryset.filter(status=status_param)

        # Date filters (timezone-safe)
        date = request.query_params.get("date")
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if date:
            parsed = parse_date(date)
            if not parsed:
                return error_response("Invalid date format. Use YYYY-MM-DD")

            start = datetime.combine(parsed, time.min)
            end = datetime.combine(parsed, time.max)
            queryset = queryset.filter(created_at__range=(start, end))

        elif from_date and to_date:
            f = parse_date(from_date)
            t = parse_date(to_date)
            if not f or not t:
                return error_response("Invalid date format. Use YYYY-MM-DD")

            queryset = queryset.filter(created_at__date__range=(f, t))

        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, "Leads retrieved successfully")

    # -------------------------
    # CONVERTED LEADS
    # -------------------------
    @action(detail=False, methods=['get'])
    def converted(self, request):
        """
        Converted leads only
        """
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
        return success_response(serializer.data, "Converted leads retrieved successfully")

    # -------------------------
    # MY LEADS
    # -------------------------
    @action(detail=False, methods=['get'])
    def my_leads(self, request):
        """
    Leads assigned to current user (active only)
    Supports: status + date
    """
        leads = Lead.objects.filter(
            assigned_to=request.user,
            converted_by__isnull=True,
            converted_at__isnull=True,
            original_type__isnull=True
        )
    
    # Status filter
        status_param = request.query_params.get("status")
        if status_param:
            leads = leads.filter(status=status_param)

        # Date filters
        date = request.query_params.get("date")
        from_date = request.query_params.get("from_date")
        to_date = request.query_params.get("to_date")

        if date:
            parsed = parse_date(date)
            if not parsed:
                return error_response("Invalid date format. Use YYYY-MM-DD")
    
            start = datetime.combine(parsed, time.min)
            end = datetime.combine(parsed, time.max)
            leads = leads.filter(created_at__range=(start, end))

        elif from_date and to_date:
            f = parse_date(from_date)
            t = parse_date(to_date)
            if not f or not t:
                return error_response("Invalid date format. Use YYYY-MM-DD")

            leads = leads.filter(created_at__date__range=(f, t))

        page = self.paginate_queryset(leads)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(leads, many=True)
        return success_response(serializer.data, "Your leads retrieved successfully")

    # -------------------------
    # CREATE
    # -------------------------
    def create(self, request):
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

    # -------------------------
    # UPDATE
    # -------------------------
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