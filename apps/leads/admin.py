from django.contrib import admin
from .models import (
    Lead,
    LeadActivity,
    FollowUp,
    PulledLead
)

# ==============================
# Inlines
# ==============================

class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ['created_at']


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0
    readonly_fields = ['created_at', 'updated_at']

# ==============================
# Lead Admin
# ==============================

@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'phone',
        'lead_type',
        'status',
        'assigned_to',
        'created_at'
    )

    list_filter = (
        'lead_type',
        'status',
        'created_at'
    )

    search_fields = (
        'name',
        'email',
        'phone',
        'company'
    )

    readonly_fields = (
        'created_at',
        'updated_at',
        'converted_at'
    )

    inlines = [
        LeadActivityInline,
        FollowUpInline,
    ]

    fieldsets = (
        ('Basic Information', {
            'fields': (
                'name',
                'email',
                'phone',
                'company',
                'city',
                'state'
            )
        }),
        ('Lead Details', {
            'fields': (
                'lead_type',
                'status',
                'notes'
            )
        }),
        ('Assignment', {
            'fields': (
                'assigned_to',
                'uploaded_by'
            )
        }),
        ('Conversion', {
            'fields': (
                'original_type',
                'converted_by',
                'converted_at'
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        }),
    )


# ==============================
# Lead Activity Admin
# ==============================

@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = (
        'lead',
        'user',
        'activity_type',
        'created_at'
    )

    list_filter = (
        'activity_type',
        'created_at'
    )

    search_fields = (
        'lead__name',
        'description'
    )

    readonly_fields = (
        'created_at',
    )


# ==============================
# Follow Up Admin
# ==============================

@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = (
        'lead',
        'assigned_to',
        'scheduled_date',
        'completed',
        'created_at'
    )

    list_filter = (
        'completed',
        'scheduled_date'
    )

    search_fields = (
        'lead__name',
        'notes'
    )

    readonly_fields = (
        'created_at',
        'updated_at'
    )


# ==============================
# Pulled Lead Admin
# ==============================
@admin.register(PulledLead)
class PulledLeadAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'phone',
        'original_lead_id',  # Add this
        'original_lead_type',
        'original_status',
        'pulled_by',
        'pulled_from',
        'exported',
        'created_at',
        'is_moved_lead'  # Add custom method
    )
    
    list_filter = (
        'original_lead_type',
        'original_status',
        'exported',
        'created_at'
    )
    
    search_fields = (
        'name',
        'phone',
        'email',
        'original_lead_id'  # Add this
    )
    
    readonly_fields = (
        'original_lead_id',  # Add this
        'name',
        'email',
        'phone',
        'company',
        'city',
        'state',
        'notes',
        'original_lead_type',
        'original_status',
        'pulled_by',
        'pulled_from',
        'pull_reason',
        'filter_criteria',
        'exported',
        'exported_at',
        'created_at',
        'updated_at'
    )
    
    fieldsets = (
        ('Lead Information (MOVED from Lead table)', {
            'fields': (
                'original_lead_id',
                'name',
                'email',
                'phone',
                'company',
                'city',
                'state',
                'notes'
            )
        }),
        ('Original Lead Details', {
            'fields': (
                'original_lead_type',
                'original_status'
            )
        }),
        ('Pull Information', {
            'fields': (
                'pulled_by',
                'pulled_from',
                'pull_reason',
                'filter_criteria'
            )
        }),
        ('Export Information', {
            'fields': (
                'exported',
                'exported_at'
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at'
            )
        }),
    )
    
    def is_moved_lead(self, obj):
        """Check if this lead was moved (not just copied)"""
        return obj.filter_criteria.get('deleted_from_lead_table', False)
    is_moved_lead.boolean = True
    is_moved_lead.short_description = 'Moved (Not Copied)'
    
    def has_add_permission(self, request):
        return True  # Prevent manual creation
    
    def has_delete_permission(self, request, obj=None):
        return True  # Protect audit/history data