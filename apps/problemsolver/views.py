from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import filters
from django_filters.rest_framework import DjangoFilterBackend
from django.db import transaction
from django.db.models import Count, Avg, Q
from django.utils import timezone
from datetime import timedelta
from django.contrib.auth import get_user_model

from .models import ProblemReport
from .serializers import (
    ProblemReportSerializer,
    ProblemReportListSerializer,
    ProblemUpdateSerializer,
    AddCommunicationSerializer,
    ProblemBulkUpdateSerializer,
    ProblemStatsSerializer
)

User = get_user_model()

# Custom response helpers
def success_response(data, message="Success"):
    return Response({
        'success': True,
        'message': message,
        'data': data
    }, status=status.HTTP_200_OK)

def error_response(message, errors=None, status_code=status.HTTP_400_BAD_REQUEST):
    response_data = {
        'success': False,
        'message': message
    }
    if errors:
        response_data['errors'] = errors
    return Response(response_data, status=status_code)

def created_response(data, message="Created successfully"):
    return Response({
        'success': True,
        'message': message,
        'data': data
    }, status=status.HTTP_201_CREATED)


class ProblemReportViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Problem Report operations
    """
    queryset = ProblemReport.objects.all()
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['status', 'priority', 'problem_type', 'is_resolved', 'assigned_to']
    search_fields = [
        'title', 'description', 'customer_name', 
        'customer_email', 'customer_phone', 'tour_package'
    ]
    ordering_fields = ['reported_date', 'due_date', 'priority', 'created_at']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return ProblemReportListSerializer
        return ProblemReportSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by customer email if provided
        customer_email = self.request.query_params.get('customer_email')
        if customer_email:
            queryset = queryset.filter(customer_email__iexact=customer_email)
        
        # Filter by customer phone if provided
        customer_phone = self.request.query_params.get('customer_phone')
        if customer_phone:
            queryset = queryset.filter(customer_phone__icontains=customer_phone)
        
        # Filter by tour package if provided
        tour_package = self.request.query_params.get('tour_package')
        if tour_package:
            queryset = queryset.filter(tour_package__icontains=tour_package)
        
        # Filter by date range
        start_date = self.request.query_params.get('start_date')
        end_date = self.request.query_params.get('end_date')
        if start_date:
            queryset = queryset.filter(reported_date__date__gte=start_date)
        if end_date:
            queryset = queryset.filter(reported_date__date__lte=end_date)
        
        # Filter by overdue status
        overdue = self.request.query_params.get('overdue')
        if overdue and overdue.lower() == 'true':
            queryset = queryset.filter(
                due_date__lt=timezone.now().date()
            ).exclude(
                status__in=['RESOLVED', 'CANCELLED']
            )
        
        # Filter by assigned to me
        my_tasks = self.request.query_params.get('my_tasks')
        if my_tasks and my_tasks.lower() == 'true':
            queryset = queryset.filter(assigned_to=self.request.user)
        
        # Filter by problem type
        problem_type = self.request.query_params.get('problem_type')
        if problem_type:
            queryset = queryset.filter(problem_type=problem_type)
        
        return queryset.select_related('assigned_to', 'reported_by')
    
    def perform_create(self, serializer):
        serializer.save(reported_by=self.request.user)
    
    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            self.perform_create(serializer)
            return created_response(serializer.data, "Problem report created successfully")
        return error_response("Validation failed", serializer.errors)
    
    def update(self, request, *args, **kwargs):
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        if serializer.is_valid():
            self.perform_update(serializer)
            return success_response(serializer.data, "Problem updated successfully")
        return error_response("Validation failed", serializer.errors)
    
    def destroy(self, request, *args, **kwargs):
        try:
            instance = self.get_object()
            instance.delete()
            return success_response(None, "Problem deleted successfully")
        except ProblemReport.DoesNotExist:
            return error_response("Problem not found")
    
    @action(detail=True, methods=['post'])
    def update_problem(self, request, pk=None):
        """Update problem details"""
        try:
            problem = self.get_object()
            serializer = ProblemUpdateSerializer(data=request.data)
            
            if not serializer.is_valid():
                return error_response("Validation failed", serializer.errors)
            
            data = serializer.validated_data
            
            # Track changes
            changes = []
            
            # Update status if provided
            if 'status' in data and data['status'] != problem.status:
                old_status = problem.status
                problem.status = data['status']
                changes.append(f"Status changed from {old_status} to {data['status']}")
            
            # Update priority if provided
            if 'priority' in data and data['priority'] != problem.priority:
                old_priority = problem.priority
                problem.priority = data['priority']
                changes.append(f"Priority changed from {old_priority} to {data['priority']}")
            
            # Update assigned_to if provided
            if 'assigned_to' in data:
                if data['assigned_to']:
                    try:
                        user = User.objects.get(id=data['assigned_to'])
                        if problem.assigned_to != user:
                            old_assignee = problem.assigned_to
                            problem.assigned_to = user
                            if old_assignee:
                                changes.append(f"Reassigned from {old_assignee.get_full_name()} to {user.get_full_name()}")
                            else:
                                changes.append(f"Assigned to {user.get_full_name()}")
                    except User.DoesNotExist:
                        return error_response("User not found")
                else:
                    if problem.assigned_to:
                        changes.append(f"Unassigned from {problem.assigned_to.get_full_name()}")
                    problem.assigned_to = None
            
            # Update due_date if provided
            if 'due_date' in data:
                old_due_date = problem.due_date
                problem.due_date = data['due_date']
                if old_due_date != data['due_date']:
                    changes.append(f"Due date changed from {old_due_date} to {data['due_date']}")
            
            # Update resolution_notes if provided
            if 'resolution_notes' in data:
                problem.resolution_notes = data['resolution_notes']
            
            # Save problem
            problem.save()
            
            # Add communication if there are changes or a message
            if changes or data.get('message'):
                message = ""
                if changes:
                    message = "Changes made:\n" + "\n".join(f"• {change}" for change in changes)
                if data.get('message'):
                    if message:
                        message += "\n\n"
                    message += data['message']
                
                problem.add_communication(
                    message=message,
                    user=request.user,
                    is_internal=data.get('is_internal', False),
                    new_status=data.get('status')
                )
            
            return success_response(
                self.get_serializer(problem).data,
                "Problem updated successfully"
            )
        except ProblemReport.DoesNotExist:
            return error_response("Problem report not found")
    
    @action(detail=True, methods=['post'])
    def add_communication(self, request, pk=None):
        """Add communication to problem"""
        try:
            problem = self.get_object()
            serializer = AddCommunicationSerializer(data=request.data)
            
            if not serializer.is_valid():
                return error_response("Validation failed", serializer.errors)
            
            data = serializer.validated_data
            
            # Add communication
            problem.add_communication(
                message=data['message'],
                user=request.user,
                is_internal=data.get('is_internal', False),
                new_status=data.get('new_status')
            )
            
            # Update status if new_status is provided
            if data.get('new_status') and data['new_status'] != problem.status:
                problem.status = data['new_status']
                problem.save()
            
            return success_response(
                self.get_serializer(problem).data,
                "Communication added successfully"
            )
        except ProblemReport.DoesNotExist:
            return error_response("Problem report not found")
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign problem to user"""
        try:
            problem = self.get_object()
            user_id = request.data.get('assigned_to')
            
            if not user_id:
                return error_response("User ID is required")
            
            try:
                user = User.objects.get(id=user_id)
                problem.assign_to(user, assigned_by=request.user)
                
                return success_response(
                    self.get_serializer(problem).data,
                    "Problem assigned successfully"
                )
            except User.DoesNotExist:
                return error_response("User not found")
        except ProblemReport.DoesNotExist:
            return error_response("Problem report not found")
    
    @action(detail=True, methods=['post'])
    def mark_resolved(self, request, pk=None):
        """Mark problem as resolved"""
        try:
            problem = self.get_object()
            resolution_notes = request.data.get('resolution_notes', '')
            
            problem.mark_resolved(resolution_notes, resolved_by=request.user)
            
            return success_response(
                self.get_serializer(problem).data,
                "Problem marked as resolved"
            )
        except ProblemReport.DoesNotExist:
            return error_response("Problem report not found")
    
    @action(detail=False, methods=['post'])
    def bulk_update(self, request):
        """Bulk update problems"""
        serializer = ProblemBulkUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)
        
        data = serializer.validated_data
        problem_ids = data['problem_ids']
        
        # Get problems
        problems = ProblemReport.objects.filter(id__in=problem_ids)
        if not problems.exists():
            return error_response("No valid problems found")
        
        updated_problems = []
        with transaction.atomic():
            for problem in problems:
                if 'status' in data and data['status'] != problem.status:
                    problem.update_status(
                        new_status=data['status'],
                        notes="Bulk update",
                        updated_by=request.user
                    )
                
                if 'assigned_to' in data:
                    user_id = data['assigned_to']
                    if user_id:
                        try:
                            user = User.objects.get(id=user_id)
                            if problem.assigned_to != user:
                                problem.assign_to(user, assigned_by=request.user)
                        except User.DoesNotExist:
                            continue
                    else:
                        problem.assigned_to = None
                        problem.add_communication(
                            message="Unassigned (bulk update)",
                            user=request.user
                        )
                        problem.save()
                
                if 'priority' in data and data['priority'] != problem.priority:
                    old_priority = problem.priority
                    problem.priority = data['priority']
                    problem.add_communication(
                        message=f"Priority changed from {old_priority} to {data['priority']} (bulk update)",
                        user=request.user
                    )
                    problem.save()
                
                updated_problems.append(problem)
        
        return success_response(
            ProblemReportListSerializer(updated_problems, many=True).data,
            f"Updated {len(updated_problems)} problems successfully"
        )
    
    @action(detail=False, methods=['get'])
    def stats(self, request):
        """Get problem statistics"""
        # Time periods
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        month_ago = today - timedelta(days=30)
        
        # Total count
        total = ProblemReport.objects.count()
        
        # Count by status
        by_status = dict(ProblemReport.objects.values_list('status').annotate(
            count=Count('id')
        ))
        
        # Count by priority
        by_priority = dict(ProblemReport.objects.values_list('priority').annotate(
            count=Count('id')
        ))
        
        # Count by type
        by_type = dict(ProblemReport.objects.values_list('problem_type').annotate(
            count=Count('id')
        ))
        
        # Average resolution time (in hours)
        avg_resolution_time_result = ProblemReport.objects.filter(
            resolution_time_minutes__isnull=False
        ).aggregate(
            avg_time=Avg('resolution_time_minutes')
        )
        avg_resolution_time = round((avg_resolution_time_result['avg_time'] or 0) / 60, 2)
        
        # Overdue unresolved problems
        unresolved_overdue = ProblemReport.objects.filter(
            due_date__lt=today
        ).exclude(
            status__in=['RESOLVED', 'CANCELLED']
        ).count()
        
        # Time-based counts
        today_count = ProblemReport.objects.filter(
            reported_date__date=today
        ).count()
        
        week_count = ProblemReport.objects.filter(
            reported_date__date__gte=week_ago
        ).count()
        
        month_count = ProblemReport.objects.filter(
            reported_date__date__gte=month_ago
        ).count()
        
        data = {
            'total': total,
            'by_status': by_status,
            'by_priority': by_priority,
            'by_type': by_type,
            'avg_resolution_time': avg_resolution_time,
            'unresolved_overdue': unresolved_overdue,
            'today_count': today_count,
            'week_count': week_count,
            'month_count': month_count
        }
        
        serializer = ProblemStatsSerializer(data=data)
        serializer.is_valid()
        
        return success_response(
            serializer.data,
            "Problem statistics retrieved successfully"
        )
    
    @action(detail=False, methods=['get'])
    def my_assigned(self, request):
        """Get problems assigned to current user"""
        queryset = self.get_queryset().filter(assigned_to=request.user)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, "Your assigned problems retrieved successfully")
    
    @action(detail=False, methods=['get'])
    def dashboard(self, request):
        """Get dashboard data"""
        # Time periods
        today = timezone.now().date()
        week_ago = today - timedelta(days=7)
        
        # Recent problems (last 7 days)
        recent_problems = ProblemReport.objects.filter(
            reported_date__date__gte=week_ago
        ).order_by('-reported_date')[:10]
        
        # Urgent problems
        urgent_problems = ProblemReport.objects.filter(
            priority='URGENT'
        ).exclude(
            status__in=['RESOLVED', 'CANCELLED']
        ).order_by('due_date')[:10]
        
        # Overdue problems
        overdue_problems = ProblemReport.objects.filter(
            due_date__lt=today
        ).exclude(
            status__in=['RESOLVED', 'CANCELLED']
        ).order_by('due_date')[:10]
        
        # Statistics
        stats = {
            'total': ProblemReport.objects.count(),
            'resolved': ProblemReport.objects.filter(status='RESOLVED').count(),
            'in_progress': ProblemReport.objects.filter(status='IN_PROGRESS').count(),
            'pending': ProblemReport.objects.filter(status='PENDING').count(),
            'urgent': ProblemReport.objects.filter(priority='URGENT').count(),
            'today': ProblemReport.objects.filter(
                reported_date__date=today
            ).count(),
            'week': ProblemReport.objects.filter(
                reported_date__date__gte=week_ago
            ).count(),
        }
        
        # Top assignees
        top_assignees = ProblemReport.objects.filter(
            assigned_to__isnull=False
        ).values(
            'assigned_to__id',
            'assigned_to__first_name',
            'assigned_to__last_name'
        ).annotate(
            total=Count('id'),
            resolved=Count('id', filter=Q(status='RESOLVED')),
            pending=Count('id', filter=~Q(status__in=['RESOLVED', 'CANCELLED']))
        ).order_by('-total')[:5]
        
        # Problem type distribution
        type_distribution = ProblemReport.objects.values(
            'problem_type'
        ).annotate(
            count=Count('id')
        ).order_by('-count')[:10]
        
        data = {
            'recent_problems': ProblemReportListSerializer(recent_problems, many=True).data,
            'urgent_problems': ProblemReportListSerializer(urgent_problems, many=True).data,
            'overdue_problems': ProblemReportListSerializer(overdue_problems, many=True).data,
            'stats': stats,
            'top_assignees': list(top_assignees),
            'type_distribution': list(type_distribution),
            'updated_at': timezone.now().isoformat()
        }
        
        return success_response(data, "Problem dashboard data retrieved successfully")
    
    @action(detail=False, methods=['get'])
    def customer_problems(self, request):
        """Get problems for a specific customer"""
        email = request.query_params.get('email')
        phone = request.query_params.get('phone')
        
        if not email and not phone:
            return error_response("Email or phone is required")
        
        queryset = self.get_queryset()
        if email:
            queryset = queryset.filter(customer_email__iexact=email)
        if phone:
            queryset = queryset.filter(customer_phone=phone)
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, "Customer problems retrieved successfully")