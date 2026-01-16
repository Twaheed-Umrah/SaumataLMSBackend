from django.urls import path
from .views import (BulkCallerPresenceAPIView, LeadViewSet, FollowUpViewSet,
                    CallerPresenceManagementAPIView,LeadPullByIDsView,LeadPullByFiltersView,
                    PulledLeadsListView,PulledLeadsExportView,PulledLeadsStatisticsView,
                    PulledLeadsPrepareUploadView,BulkLeadPullPreviewView,CallerLeadsSummaryView,
                    TransferPulledLeadsView,TransferByFiltersView,PreviewTransferByFiltersView
                    ,LeadManualCreateAPIView)

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
lead_upload_manual = LeadViewSet.as_view({'post': 'upload_manual'})
followup_complete = FollowUpViewSet.as_view({'post': 'complete'})
followup_pending = FollowUpViewSet.as_view({'get': 'pending'})
caller_presence = CallerPresenceManagementAPIView.as_view()
bulk_caller_presence = BulkCallerPresenceAPIView.as_view()
pull_by_ids = LeadPullByIDsView.as_view()
pull_by_filters = LeadPullByFiltersView.as_view()
pulled_leads_list = PulledLeadsListView.as_view()
pulled_leads_export = PulledLeadsExportView.as_view()
pulled_leads_stats = PulledLeadsStatisticsView.as_view()
pulled_prepare_upload = PulledLeadsPrepareUploadView.as_view()
pull_preview = BulkLeadPullPreviewView.as_view()
caller_summary = CallerLeadsSummaryView.as_view()
transfer_pulled_leads = TransferPulledLeadsView.as_view()
transfer_by_filters = TransferByFiltersView.as_view()
preview_transfer_filters = PreviewTransferByFiltersView.as_view()

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
    path('leads/upload/manual/', lead_upload_manual, name='lead-upload-manual'),
    # =========================
    # FollowUp APIs
    # =========================
    path('followups/', followup_list, name='followup-list'),
    path('followups/pending/', followup_pending, name='followup-pending'),
    path('followups/<int:pk>/', followup_detail, name='followup-detail'),
    path('followups/<int:pk>/complete/', followup_complete, name='followup-complete'),
    path('callers/<int:caller_id>/presence/', caller_presence, name='caller-presence'),
    path('callers/bulk-presence/', bulk_caller_presence, name='bulk-caller-presence'),

     path('leads/pull/by-ids/', pull_by_ids, name='lead-pull-by-ids'),
    path('leads/pull/by-filters/', pull_by_filters, name='lead-pull-by-filters'),
    path('leads/pull/preview/', pull_preview, name='lead-pull-preview'),
    path('leads/pull/caller-summary/', caller_summary, name='caller-leads-summary'),
    
    path('leads/pulled/', pulled_leads_list, name='pulled-leads-list'),
    path('leads/pulled/export/', pulled_leads_export, name='pulled-leads-export'),
    path('leads/pulled/statistics/', pulled_leads_stats, name='pulled-leads-stats'),
    path('leads/pulled/prepare-upload/', pulled_prepare_upload, name='pulled-prepare-upload'),

    path('leads/transfer/pulled/', transfer_pulled_leads, name='transfer-pulled-leads'),
    path('leads/transfer/by-filters/', transfer_by_filters, name='transfer-by-filters'),
    path('leads/transfer/preview-filters/', preview_transfer_filters, name='preview-transfer-filters'),
    path('leads/create/manual/', LeadManualCreateAPIView.as_view(), name='lead-create-manual'),
    
]
