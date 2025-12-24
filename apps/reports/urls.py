# dashboard/urls.py
from django.urls import path
from .views import (
    DashboardView,
    caller_performance,
    lead_funnel,
    sales_report,
    conversion_report,
    recent_activities,
    upcoming_followups
)

urlpatterns = [
    path('', DashboardView.as_view(), name='dashboard'),
    path('caller-performance/', caller_performance, name='caller-performance'),
    path('lead-funnel/', lead_funnel, name='lead-funnel'),
    path('sales-report/', sales_report, name='sales-report'),
    path('conversion-report/', conversion_report, name='conversion-report'),
    path('recent-activities/', recent_activities, name='recent-activities'),
    path('upcoming-followups/', upcoming_followups, name='upcoming-followups'),
]