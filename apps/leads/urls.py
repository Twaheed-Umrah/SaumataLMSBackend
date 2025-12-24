from django.urls import path
from .views import LeadViewSet, FollowUpViewSet

# =========================
# Lead ViewSet mappings
# =========================
lead_list = LeadViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

lead_detail = LeadViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'put': 'update'
})

lead_upload = LeadViewSet.as_view({'post': 'upload'})
lead_convert = LeadViewSet.as_view({'post': 'convert'})
lead_my = LeadViewSet.as_view({'get': 'my_leads'})
lead_converted = LeadViewSet.as_view({'get': 'converted'})
lead_add_activity = LeadViewSet.as_view({'post': 'add_activity'})


# =========================
# FollowUp ViewSet mappings
# =========================
followup_list = FollowUpViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

followup_detail = FollowUpViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'put': 'update'
})

followup_complete = FollowUpViewSet.as_view({'post': 'complete'})
followup_pending = FollowUpViewSet.as_view({'get': 'pending'})


urlpatterns = [
    # =========================
    # Lead APIs
    # =========================
    path('leads/', lead_list, name='lead-list'),
    path('leads/upload/', lead_upload, name='lead-upload'),
    path('leads/my/', lead_my, name='my-leads'),
    path('leads/converted/', lead_converted, name='converted-leads'),
    path('leads/<int:pk>/', lead_detail, name='lead-detail'),
    path('leads/<int:pk>/convert/', lead_convert, name='lead-convert'),
    path('leads/<int:pk>/activity/', lead_add_activity, name='lead-add-activity'),

    # =========================
    # FollowUp APIs
    # =========================
    path('followups/', followup_list, name='followup-list'),
    path('followups/pending/', followup_pending, name='followup-pending'),
    path('followups/<int:pk>/', followup_detail, name='followup-detail'),
    path('followups/<int:pk>/complete/', followup_complete, name='followup-complete'),
]
