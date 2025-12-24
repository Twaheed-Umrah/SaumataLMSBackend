# dashboard/views.py
from rest_framework.views import APIView
from rest_framework.decorators import api_view, permission_classes
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
from apps.leads.models import Lead, LeadActivity, FollowUp
from apps.sales.models import SalesReceipt, DeliveryServiceItem
from apps.accounts.models import User
from utils.constants import UserRole, LeadType, LeadStatus, PaymentStatus, DeliveryStatus
from rest_framework.permissions import IsAuthenticated
from utils.response import success_response


class DashboardView(APIView):
    """
    Dashboard statistics with role-based data filtering
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get dashboard statistics based on user role"""
        user = request.user
        data = {}
        
        # SUPER_ADMIN: See everything
        if user.role == UserRole.SUPER_ADMIN:
            data = self._get_super_admin_dashboard()
        
        # TEAM_LEADER: See all except other team leaders and super admin
        elif user.role == UserRole.TEAM_LEADER:
            data = self._get_team_leader_dashboard(user)
        
        # FRANCHISE_CALLER: See only franchise-related data
        elif user.role == UserRole.FRANCHISE_CALLER:
            data = self._get_franchise_caller_dashboard(user)
        
        # PACKAGE_CALLER: See only package-related data
        elif user.role == UserRole.PACKAGE_CALLER:
            data = self._get_package_caller_dashboard(user)
        
        # Add common user info
        data['user'] = {
            'id': user.id,
            'username': user.username,
            'full_name': user.get_full_name(),
            'role': user.role,
            'role_display': user.get_role_display(),
            'email': user.email,
            'phone': user.phone
        }
        
        return success_response(data, "Dashboard data retrieved successfully")
    
    def _get_super_admin_dashboard(self):
        """Get dashboard data for SUPER_ADMIN"""
        # Lead Statistics
        total_leads = Lead.objects.count()
        franchise_leads = Lead.objects.filter(lead_type=LeadType.FRANCHISE).count()
        package_leads = Lead.objects.filter(lead_type=LeadType.PACKAGE).count()
        
        # Lead Status Counts
        status_counts = {}
        for status_choice in LeadStatus.CHOICES:
            status_code = status_choice[0]
            count = Lead.objects.filter(status=status_code).count()
            status_counts[status_code] = {
                'count': count,
                'display': status_choice[1]
            }
        
        # Sales Statistics
        sales_data = SalesReceipt.objects.aggregate(
            total_budget=Sum('total_budget'),
            total_paid=Sum('paid_amount'),
            total_receipts=Count('id')
        )
        
        total_pending = (sales_data['total_budget'] or 0) - (sales_data['total_paid'] or 0)
        
        # User Statistics
        user_counts = {}
        for role_choice in UserRole.CHOICES:
            role_code = role_choice[0]
            count = User.objects.filter(role=role_code, is_active=True).count()
            user_counts[role_code] = {
                'count': count,
                'display': role_choice[1]
            }
        
        # Service Delivery Statistics
        service_status_counts = {}
        for status_choice in DeliveryStatus.CHOICES:
            status_code = status_choice[0]
            count = DeliveryServiceItem.objects.filter(status=status_code).count()
            service_status_counts[status_code] = {
                'count': count,
                'display': status_choice[1]
            }
        
        # Recent Activities (Last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_leads = Lead.objects.filter(created_at__gte=week_ago).count()
        recent_activities = LeadActivity.objects.filter(created_at__gte=week_ago).count()
        
        # Pending Follow-ups
        pending_followups = FollowUp.objects.filter(
            completed=False,
            scheduled_date__lte=timezone.now() + timedelta(days=7)
        ).count()
        
        # Today's follow-ups
        today = timezone.now().date()
        todays_followups = FollowUp.objects.filter(
            scheduled_date__date=today,
            completed=False
        ).count()
        
        return {
            'leads': {
                'total': total_leads,
                'franchise': franchise_leads,
                'package': package_leads,
                'by_status': status_counts,
                'recent': recent_leads
            },
            'sales': {
                'total_receipts': sales_data['total_receipts'] or 0,
                'total_budget': sales_data['total_budget'] or 0,
                'total_paid': sales_data['total_paid'] or 0,
                'total_pending': total_pending,
                'receipts_issued': SalesReceipt.objects.filter(is_receipt_issued=True).count()
            },
            'users': user_counts,
            'services': {
                'total': DeliveryServiceItem.objects.count(),
                'completed': DeliveryServiceItem.objects.filter(is_completed=True).count(),
                'by_status': service_status_counts
            },
            'activities': {
                'recent': recent_activities,
                'pending_followups': pending_followups,
                'todays_followups': todays_followups
            }
        }
    
    def _get_team_leader_dashboard(self, user):
        """Get dashboard data for TEAM_LEADER"""
        # Get all callers under this team leader
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
        
        # Leads assigned to team's callers
        team_leads = Lead.objects.filter(assigned_to__in=callers)
        total_leads = team_leads.count()
        
        # Lead counts by type
        franchise_leads = team_leads.filter(lead_type=LeadType.FRANCHISE).count()
        package_leads = team_leads.filter(lead_type=LeadType.PACKAGE).count()
        
        # Lead Status Counts for team
        status_counts = {}
        for status_choice in LeadStatus.CHOICES:
            status_code = status_choice[0]
            count = team_leads.filter(status=status_code).count()
            status_counts[status_code] = {
                'count': count,
                'display': status_choice[1]
            }
        
        # Team performance - conversions by team members
        team_conversions = Lead.objects.filter(
            converted_by__in=callers,
            status=LeadStatus.CONVERTED
        ).count()
        
        # Recent Activities
        week_ago = timezone.now() - timedelta(days=7)
        recent_leads = team_leads.filter(created_at__gte=week_ago).count()
        
        # Team's follow-ups
        team_followups = FollowUp.objects.filter(
            assigned_to__in=callers,
            completed=False,
            scheduled_date__lte=timezone.now() + timedelta(days=7)
        ).count()
        
        # Today's follow-ups for team
        today = timezone.now().date()
        todays_team_followups = FollowUp.objects.filter(
            assigned_to__in=callers,
            scheduled_date__date=today,
            completed=False
        ).count()
        
        # Caller statistics
        caller_stats = []
        for caller in callers:
            assigned = Lead.objects.filter(assigned_to=caller).count()
            contacted = Lead.objects.filter(
                assigned_to=caller,
                status__in=[LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP]
            ).count()
            converted = Lead.objects.filter(converted_by=caller).count()
            
            caller_stats.append({
                'id': caller.id,
                'name': caller.get_full_name(),
                'role': caller.get_role_display(),
                'assigned_leads': assigned,
                'contacted_leads': contacted,
                'converted_leads': converted,
                'conversion_rate': round((converted / assigned * 100) if assigned > 0 else 0, 2)
            })
        
        return {
            'team': {
                'total_callers': callers.count(),
                'total_leads': total_leads,
                'franchise_leads': franchise_leads,
                'package_leads': package_leads,
                'team_conversions': team_conversions,
                'caller_stats': caller_stats
            },
            'leads': {
                'total': total_leads,
                'franchise': franchise_leads,
                'package': package_leads,
                'by_status': status_counts,
                'recent': recent_leads
            },
            'activities': {
                'pending_followups': team_followups,
                'todays_followups': todays_team_followups
            }
        }
    
    def _get_franchise_caller_dashboard(self, user):
        """Get dashboard data for FRANCHISE_CALLER"""
        # Only franchise leads assigned to this caller
        my_leads = Lead.objects.filter(
            assigned_to=user,
            lead_type=LeadType.FRANCHISE
        )
        
        total_leads = my_leads.count()
        
        # Lead Status Counts
        status_counts = {}
        for status_choice in LeadStatus.CHOICES:
            status_code = status_choice[0]
            count = my_leads.filter(status=status_code).count()
            status_counts[status_code] = {
                'count': count,
                'display': status_choice[1]
            }
        
        # My conversions
        my_conversions = Lead.objects.filter(
            converted_by=user,
            lead_type=LeadType.FRANCHISE
        ).count()
        
        # Recent leads (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_leads = my_leads.filter(created_at__gte=week_ago).count()
        
        # My follow-ups
        my_followups = FollowUp.objects.filter(
            assigned_to=user,
            completed=False,
            scheduled_date__lte=timezone.now() + timedelta(days=7)
        ).count()
        
        # Today's follow-ups
        today = timezone.now().date()
        todays_followups = FollowUp.objects.filter(
            assigned_to=user,
            scheduled_date__date=today,
            completed=False
        ).count()
        
        # Recent activities
        recent_activities = LeadActivity.objects.filter(
            user=user,
            created_at__gte=week_ago
        ).count()
        
        return {
            'my_stats': {
                'total_leads': total_leads,
                'contacted_leads': my_leads.filter(
                    status__in=[LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP]
                ).count(),
                'converted_leads': my_conversions,
                'conversion_rate': round((my_conversions / total_leads * 100) if total_leads > 0 else 0, 2)
            },
            'leads': {
                'total': total_leads,
                'by_status': status_counts,
                'recent': recent_leads
            },
            'activities': {
                'recent_activities': recent_activities,
                'pending_followups': my_followups,
                'todays_followups': todays_followups,
                'upcoming_followups': FollowUp.objects.filter(
                    assigned_to=user,
                    completed=False,
                    scheduled_date__gt=timezone.now()
                ).count()
            }
        }
    
    def _get_package_caller_dashboard(self, user):
        """Get dashboard data for PACKAGE_CALLER"""
        # Only package leads assigned to this caller
        my_leads = Lead.objects.filter(
            assigned_to=user,
            lead_type=LeadType.PACKAGE
        )
        
        total_leads = my_leads.count()
        
        # Lead Status Counts
        status_counts = {}
        for status_choice in LeadStatus.CHOICES:
            status_code = status_choice[0]
            count = my_leads.filter(status=status_code).count()
            status_counts[status_code] = {
                'count': count,
                'display': status_choice[1]
            }
        
        # My conversions
        my_conversions = Lead.objects.filter(
            converted_by=user,
            lead_type=LeadType.PACKAGE
        ).count()
        
        # Recent leads (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_leads = my_leads.filter(created_at__gte=week_ago).count()
        
        # My follow-ups
        my_followups = FollowUp.objects.filter(
            assigned_to=user,
            completed=False,
            scheduled_date__lte=timezone.now() + timedelta(days=7)
        ).count()
        
        # Today's follow-ups
        today = timezone.now().date()
        todays_followups = FollowUp.objects.filter(
            assigned_to=user,
            scheduled_date__date=today,
            completed=False
        ).count()
        
        # Recent activities
        recent_activities = LeadActivity.objects.filter(
            user=user,
            created_at__gte=week_ago
        ).count()
        
        return {
            'my_stats': {
                'total_leads': total_leads,
                'contacted_leads': my_leads.filter(
                    status__in=[LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP]
                ).count(),
                'converted_leads': my_conversions,
                'conversion_rate': round((my_conversions / total_leads * 100) if total_leads > 0 else 0, 2)
            },
            'leads': {
                'total': total_leads,
                'by_status': status_counts,
                'recent': recent_leads
            },
            'activities': {
                'recent_activities': recent_activities,
                'pending_followups': my_followups,
                'todays_followups': todays_followups,
                'upcoming_followups': FollowUp.objects.filter(
                    assigned_to=user,
                    completed=False,
                    scheduled_date__gt=timezone.now()
                ).count()
            }
        }


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def caller_performance(request):
    """
    Get performance metrics for callers with role-based access
    """
    user = request.user
    
    if user.role == UserRole.SUPER_ADMIN:
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
    elif user.role == UserRole.TEAM_LEADER:
        # Team leader can see all callers
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
    else:
        # Callers can only see their own performance
        callers = User.objects.filter(id=user.id, is_active=True)
    
    performance_data = []
    
    for caller in callers:
        # Leads assigned by type
        franchise_leads = Lead.objects.filter(
            assigned_to=caller,
            lead_type=LeadType.FRANCHISE
        ).count()
        
        package_leads = Lead.objects.filter(
            assigned_to=caller,
            lead_type=LeadType.PACKAGE
        ).count()
        
        total_assigned = franchise_leads + package_leads
        
        # Leads contacted
        contacted_leads = Lead.objects.filter(
            assigned_to=caller,
            status__in=[LeadStatus.CONTACTED, LeadStatus.INTERESTED, LeadStatus.FOLLOW_UP]
        ).count()
        
        # Leads converted by type
        franchise_conversions = Lead.objects.filter(
            converted_by=caller,
            lead_type=LeadType.FRANCHISE
        ).count()
        
        package_conversions = Lead.objects.filter(
            converted_by=caller,
            lead_type=LeadType.PACKAGE
        ).count()
        
        total_conversions = franchise_conversions + package_conversions
        
        # Conversion rates
        franchise_rate = round((franchise_conversions / franchise_leads * 100) if franchise_leads > 0 else 0, 2)
        package_rate = round((package_conversions / package_leads * 100) if package_leads > 0 else 0, 2)
        overall_rate = round((total_conversions / total_assigned * 100) if total_assigned > 0 else 0, 2)
        
        # Activities count
        activities = LeadActivity.objects.filter(user=caller).count()
        
        # Recent activities (last 7 days)
        week_ago = timezone.now() - timedelta(days=7)
        recent_activities = LeadActivity.objects.filter(
            user=caller,
            created_at__gte=week_ago
        ).count()
        
        performance_data.append({
            'caller_id': caller.id,
            'caller_name': caller.get_full_name(),
            'role': caller.get_role_display(),
            'assigned_leads': {
                'total': total_assigned,
                'franchise': franchise_leads,
                'package': package_leads
            },
            'contacted_leads': contacted_leads,
            'converted_leads': {
                'total': total_conversions,
                'franchise': franchise_conversions,
                'package': package_conversions
            },
            'conversion_rate': {
                'franchise': franchise_rate,
                'package': package_rate,
                'overall': overall_rate
            },
            'activities': {
                'total': activities,
                'recent': recent_activities
            }
        })
    
    return success_response(performance_data, "Caller performance retrieved successfully")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def lead_funnel(request):
    """
    Get lead funnel statistics with role-based filtering
    """
    user = request.user
    
    if user.role == UserRole.SUPER_ADMIN:
        # All leads
        funnel_data = {
            'new': Lead.objects.filter(status=LeadStatus.NEW).count(),
            'contacted': Lead.objects.filter(status=LeadStatus.CONTACTED).count(),
            'interested': Lead.objects.filter(status=LeadStatus.INTERESTED).count(),
            'follow_up': Lead.objects.filter(status=LeadStatus.FOLLOW_UP).count(),
            'converted': Lead.objects.filter(status=LeadStatus.CONVERTED).count(),
            'lost': Lead.objects.filter(status=LeadStatus.LOST).count(),
            'not_interested': Lead.objects.filter(status=LeadStatus.NOT_INTERESTED).count()
        }
        
        # Add type breakdown
        funnel_data['franchise'] = {
            'new': Lead.objects.filter(status=LeadStatus.NEW, lead_type=LeadType.FRANCHISE).count(),
            'converted': Lead.objects.filter(status=LeadStatus.CONVERTED, lead_type=LeadType.FRANCHISE).count()
        }
        
        funnel_data['package'] = {
            'new': Lead.objects.filter(status=LeadStatus.NEW, lead_type=LeadType.PACKAGE).count(),
            'converted': Lead.objects.filter(status=LeadStatus.CONVERTED, lead_type=LeadType.PACKAGE).count()
        }
        
    elif user.role == UserRole.TEAM_LEADER:
        # Team's leads
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
        team_leads = Lead.objects.filter(assigned_to__in=callers)
        
        funnel_data = {
            'new': team_leads.filter(status=LeadStatus.NEW).count(),
            'contacted': team_leads.filter(status=LeadStatus.CONTACTED).count(),
            'interested': team_leads.filter(status=LeadStatus.INTERESTED).count(),
            'follow_up': team_leads.filter(status=LeadStatus.FOLLOW_UP).count(),
            'converted': team_leads.filter(status=LeadStatus.CONVERTED).count(),
            'lost': team_leads.filter(status=LeadStatus.LOST).count(),
            'not_interested': team_leads.filter(status=LeadStatus.NOT_INTERESTED).count()
        }
        
    elif user.role == UserRole.FRANCHISE_CALLER:
        # Only franchise leads assigned to this caller
        my_leads = Lead.objects.filter(assigned_to=user, lead_type=LeadType.FRANCHISE)
        
        funnel_data = {
            'new': my_leads.filter(status=LeadStatus.NEW).count(),
            'contacted': my_leads.filter(status=LeadStatus.CONTACTED).count(),
            'interested': my_leads.filter(status=LeadStatus.INTERESTED).count(),
            'follow_up': my_leads.filter(status=LeadStatus.FOLLOW_UP).count(),
            'converted': my_leads.filter(status=LeadStatus.CONVERTED).count(),
            'lost': my_leads.filter(status=LeadStatus.LOST).count(),
            'not_interested': my_leads.filter(status=LeadStatus.NOT_INTERESTED).count()
        }
        
    elif user.role == UserRole.PACKAGE_CALLER:
        # Only package leads assigned to this caller
        my_leads = Lead.objects.filter(assigned_to=user, lead_type=LeadType.PACKAGE)
        
        funnel_data = {
            'new': my_leads.filter(status=LeadStatus.NEW).count(),
            'contacted': my_leads.filter(status=LeadStatus.CONTACTED).count(),
            'interested': my_leads.filter(status=LeadStatus.INTERESTED).count(),
            'follow_up': my_leads.filter(status=LeadStatus.FOLLOW_UP).count(),
            'converted': my_leads.filter(status=LeadStatus.CONVERTED).count(),
            'lost': my_leads.filter(status=LeadStatus.LOST).count(),
            'not_interested': my_leads.filter(status=LeadStatus.NOT_INTERESTED).count()
        }
    
    return success_response(funnel_data, "Lead funnel data retrieved successfully")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def sales_report(request):
    """
    Get sales report with filters and role-based access
    """
    user = request.user
    
    # Get query parameters
    start_date = request.query_params.get('start_date')
    end_date = request.query_params.get('end_date')
    
    # Base queryset with role-based filtering
    if user.role == UserRole.SUPER_ADMIN:
        queryset = SalesReceipt.objects.all()
    elif user.role == UserRole.TEAM_LEADER:
        queryset = SalesReceipt.objects.all()  # Team leaders can see all sales
    else:
        queryset = SalesReceipt.objects.none()  # Callers don't see sales reports
    
    # Apply date filters
    if start_date:
        queryset = queryset.filter(sale_date__gte=start_date)
    if end_date:
        queryset = queryset.filter(sale_date__lte=end_date)
    
    # Aggregations
    summary = queryset.aggregate(
        total_receipts=Count('id'),
        total_budget=Sum('total_budget'),
        total_paid=Sum('paid_amount')
    )
    
    total_pending = (summary['total_budget'] or 0) - (summary['total_paid'] or 0)
    
    # Payment status breakdown
    status_breakdown = {}
    for status_choice in PaymentStatus.CHOICES:
        status_code = status_choice[0]
        receipts = queryset.filter(payment_status=status_code)
        count = receipts.count()
        budget = receipts.aggregate(total=Sum('total_budget'))['total'] or 0
        paid = receipts.aggregate(total=Sum('paid_amount'))['total'] or 0
        
        status_breakdown[status_code] = {
            'count': count,
            'budget': budget,
            'paid': paid,
            'pending': budget - paid,
            'display': status_choice[1]
        }
    
    # Monthly breakdown for charts
    monthly_data = {}
    for i in range(5, -1, -1):  # Last 6 months
        month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_start = month_start - timedelta(days=30*i)
        month_end = month_start + timedelta(days=30)
        
        month_receipts = queryset.filter(
            sale_date__gte=month_start,
            sale_date__lt=month_end
        )
        
        monthly_data[month_start.strftime('%b %Y')] = {
            'receipts': month_receipts.count(),
            'budget': month_receipts.aggregate(total=Sum('total_budget'))['total'] or 0,
            'paid': month_receipts.aggregate(total=Sum('paid_amount'))['total'] or 0
        }
    
    data = {
        'summary': {
            'total_receipts': summary['total_receipts'] or 0,
            'total_budget': summary['total_budget'] or 0,
            'total_paid': summary['total_paid'] or 0,
            'total_pending': total_pending,
            'receipts_issued': queryset.filter(is_receipt_issued=True).count()
        },
        'status_breakdown': status_breakdown,
        'monthly_breakdown': monthly_data
    }
    
    return success_response(data, "Sales report retrieved successfully")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def conversion_report(request):
    """
    Get conversion report with role-based access
    """
    user = request.user
    
    if user.role == UserRole.SUPER_ADMIN:
        # Total conversions
        total_conversions = Lead.objects.filter(status=LeadStatus.CONVERTED).count()
        
        # Conversions by type
        franchise_conversions = Lead.objects.filter(
            status=LeadStatus.CONVERTED,
            lead_type=LeadType.FRANCHISE
        ).count()
        
        package_conversions = Lead.objects.filter(
            status=LeadStatus.CONVERTED,
            lead_type=LeadType.PACKAGE
        ).count()
        
        # Lead type changes
        type_changes = Lead.objects.filter(
            original_type__isnull=False
        ).values('original_type', 'lead_type').annotate(
            count=Count('id')
        )
        
        # Top converters
        top_converters = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER]
        ).annotate(
            conversion_count=Count('converted_leads')
        ).order_by('-conversion_count')[:10]
        
        top_converters_data = [{
            'id': user.id,
            'name': user.get_full_name(),
            'role': user.get_role_display(),
            'conversions': user.conversion_count,
            'franchise_conversions': Lead.objects.filter(
                converted_by=user,
                lead_type=LeadType.FRANCHISE
            ).count(),
            'package_conversions': Lead.objects.filter(
                converted_by=user,
                lead_type=LeadType.PACKAGE
            ).count()
        } for user in top_converters]
        
        # Monthly conversion trend
        monthly_conversions = {}
        for i in range(5, -1, -1):  # Last 6 months
            month_start = timezone.now().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
            month_start = month_start - timedelta(days=30*i)
            month_end = month_start + timedelta(days=30)
            
            month_conv = Lead.objects.filter(
                status=LeadStatus.CONVERTED,
                converted_at__gte=month_start,
                converted_at__lt=month_end
            )
            
            monthly_conversions[month_start.strftime('%b %Y')] = {
                'total': month_conv.count(),
                'franchise': month_conv.filter(lead_type=LeadType.FRANCHISE).count(),
                'package': month_conv.filter(lead_type=LeadType.PACKAGE).count()
            }
        
        data = {
            'overall': {
                'total_conversions': total_conversions,
                'franchise_conversions': franchise_conversions,
                'package_conversions': package_conversions,
                'conversion_rate': round((total_conversions / Lead.objects.count() * 100) if Lead.objects.count() > 0 else 0, 2)
            },
            'type_changes': list(type_changes),
            'top_converters': top_converters_data,
            'monthly_trend': monthly_conversions
        }
    
    elif user.role == UserRole.TEAM_LEADER:
        # Team's conversions
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
        
        team_conversions = Lead.objects.filter(
            status=LeadStatus.CONVERTED,
            converted_by__in=callers
        )
        
        total_conversions = team_conversions.count()
        
        # Conversions by type
        franchise_conversions = team_conversions.filter(lead_type=LeadType.FRANCHISE).count()
        package_conversions = team_conversions.filter(lead_type=LeadType.PACKAGE).count()
        
        # Individual caller conversions
        caller_conversions = []
        for caller in callers:
            conv = Lead.objects.filter(converted_by=caller, status=LeadStatus.CONVERTED)
            caller_conversions.append({
                'id': caller.id,
                'name': caller.get_full_name(),
                'role': caller.get_role_display(),
                'total': conv.count(),
                'franchise': conv.filter(lead_type=LeadType.FRANCHISE).count(),
                'package': conv.filter(lead_type=LeadType.PACKAGE).count()
            })
        
        data = {
            'team': {
                'total_conversions': total_conversions,
                'franchise_conversions': franchise_conversions,
                'package_conversions': package_conversions,
                'caller_conversions': caller_conversions
            }
        }
    
    elif user.role == UserRole.FRANCHISE_CALLER:
        # My franchise conversions
        my_conversions = Lead.objects.filter(
            converted_by=user,
            lead_type=LeadType.FRANCHISE,
            status=LeadStatus.CONVERTED
        )
        
        data = {
            'my_conversions': {
                'total': my_conversions.count(),
                'recent': my_conversions.filter(
                    converted_at__gte=timezone.now() - timedelta(days=30)
                ).count()
            }
        }
    
    elif user.role == UserRole.PACKAGE_CALLER:
        # My package conversions
        my_conversions = Lead.objects.filter(
            converted_by=user,
            lead_type=LeadType.PACKAGE,
            status=LeadStatus.CONVERTED
        )
        
        data = {
            'my_conversions': {
                'total': my_conversions.count(),
                'recent': my_conversions.filter(
                    converted_at__gte=timezone.now() - timedelta(days=30)
                ).count()
            }
        }
    
    return success_response(data, "Conversion report retrieved successfully")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def recent_activities(request):
    """
    Get recent activities with role-based filtering
    """
    user = request.user
    
    # Base queryset
    if user.role == UserRole.SUPER_ADMIN:
        activities = LeadActivity.objects.all()
    elif user.role == UserRole.TEAM_LEADER:
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
        activities = LeadActivity.objects.filter(user__in=callers)
    else:
        activities = LeadActivity.objects.filter(user=user)
    
    # Get last 50 activities
    recent_activities = activities.select_related('lead', 'user').order_by('-created_at')[:50]
    
    activity_list = []
    for activity in recent_activities:
        activity_list.append({
            'id': activity.id,
            'lead_id': activity.lead_id,
            'lead_name': activity.lead.name,
            'user_id': activity.user_id,
            'user_name': activity.user.get_full_name(),
            'activity_type': activity.activity_type,
            'description': activity.description,
            'old_status': activity.old_status,
            'new_status': activity.new_status,
            'created_at': activity.created_at
        })
    
    return success_response(activity_list, "Recent activities retrieved successfully")


@api_view(['GET'])
@permission_classes([IsAuthenticated])
def upcoming_followups(request):
    """
    Get upcoming follow-ups with role-based filtering
    """
    user = request.user
    
    # Base queryset
    if user.role == UserRole.SUPER_ADMIN:
        followups = FollowUp.objects.filter(completed=False)
    elif user.role == UserRole.TEAM_LEADER:
        callers = User.objects.filter(
            role__in=[UserRole.FRANCHISE_CALLER, UserRole.PACKAGE_CALLER],
            is_active=True
        )
        followups = FollowUp.objects.filter(assigned_to__in=callers, completed=False)
    else:
        followups = FollowUp.objects.filter(assigned_to=user, completed=False)
    
    # Get upcoming follow-ups (next 7 days)
    upcoming = followups.filter(
        scheduled_date__gte=timezone.now(),
        scheduled_date__lte=timezone.now() + timedelta(days=7)
    ).select_related('lead', 'assigned_to').order_by('scheduled_date')
    
    followup_list = []
    for followup in upcoming:
        followup_list.append({
            'id': followup.id,
            'lead_id': followup.lead_id,
            'lead_name': followup.lead.name,
            'lead_type': followup.lead.lead_type,
            'lead_status': followup.lead.status,
            'assigned_to_id': followup.assigned_to_id,
            'assigned_to_name': followup.assigned_to.get_full_name(),
            'scheduled_date': followup.scheduled_date,
            'notes': followup.notes,
            'created_at': followup.created_at
        })
    
    return success_response(followup_list, "Upcoming follow-ups retrieved successfully")