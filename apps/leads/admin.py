from django.contrib import admin
from django.utils.html import format_html
from .models import (
    Lead,
    LeadActivity,
    FollowUp,
    PulledLead,
    PulledLeadTransferLog
)

# ==============================
# Inlines
# ==============================

class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ('created_at',)


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0
    readonly_fields = ('created_at', 'updated_at')


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
        'created_at',
    )

    list_filter = (
        'lead_type',
        'status',
        'created_at',
    )

    search_fields = (
        'name',
        'email',
        'phone',
        'company',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
        'converted_at',
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
                'state',
            )
        }),
        ('Lead Details', {
            'fields': (
                'lead_type',
                'status',
                'notes',
            )
        }),
        ('Assignment', {
            'fields': (
                'assigned_to',
                'uploaded_by',
            )
        }),
        ('Conversion', {
            'fields': (
                'original_type',
                'converted_by',
                'converted_at',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
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
        'short_description',
        'created_at',
    )

    list_filter = (
        'activity_type',
        'created_at',
    )

    search_fields = (
        'lead__name',
        'description',
        'user__username',
    )

    readonly_fields = (
        'created_at',
    )
    
    def short_description(self, obj):
        """Show first 50 characters of description"""
        if len(obj.description) > 50:
            return f"{obj.description[:50]}..."
        return obj.description
    short_description.short_description = 'Description'


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
        'created_at',
    )

    list_filter = (
        'completed',
        'scheduled_date',
    )

    search_fields = (
        'lead__name',
        'notes',
        'assigned_to__username',
    )

    readonly_fields = (
        'created_at',
        'updated_at',
    )


# ==============================
# Pulled Lead Admin
# ==============================

@admin.register(PulledLead)
class PulledLeadAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'phone',
        'original_lead_type',
        'original_status',
        'pulled_from',
        'exported',
        'created_at',
        'is_moved_lead',
    )
    
    date_hierarchy = 'created_at'
    list_per_page = 50

    list_filter = (
        'original_lead_type',
        'original_status',
        'exported',
        'created_at',
    )

    search_fields = (
        'name',
        'phone',
        'email',
        'original_lead_id',
    )

    readonly_fields = (
        'original_lead_id',
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
        'updated_at',
    )

    fieldsets = (
        ('Lead Information (Moved from Lead table)', {
            'fields': (
                'original_lead_id',
                'name',
                'email',
                'phone',
                'company',
                'city',
                'state',
                'notes',
            )
        }),
        ('Original Lead Details', {
            'fields': (
                'original_lead_type',
                'original_status',
            )
        }),
        ('Pull Information', {
            'fields': (
                'pulled_by',
                'pulled_from',
                'pull_reason',
                'filter_criteria',
            )
        }),
        ('Export Information', {
            'fields': (
                'exported',
                'exported_at',
            )
        }),
        ('Timestamps', {
            'fields': (
                'created_at',
                'updated_at',
            )
        }),
    )

    def is_moved_lead(self, obj):
        """
        True if lead was removed from Lead table (not just copied)
        """
        return obj.filter_criteria.get('deleted_from_lead_table', False)

    is_moved_lead.boolean = True
    is_moved_lead.short_description = 'Moved (Not Copied)'

    def has_add_permission(self, request):
        return True   # prevent manual creation

    def has_delete_permission(self, request, obj=None):
        return True   # protect audit data


# ==============================
# Pulled Lead Transfer Log Admin
# ==============================

@admin.register(PulledLeadTransferLog)
class PulledLeadTransferLogAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'transferred_to_info',
        'transferred_by_info',
        'lead_count',
        'transferred_at',
        'original_lead_id_display',
    )
    
    date_hierarchy = 'transferred_at'
    list_per_page = 50

    list_filter = (
        'transferred_at',
        'transferred_by',
        'transferred_to',
    )

    search_fields = (
        'original_pulled_lead_id',
        'transferred_to__username',
        'transferred_to__first_name',
        'transferred_to__last_name',
        'transferred_by__username',
        'transferred_by__first_name',
        'transferred_by__last_name',
    )

    readonly_fields = (
        'original_pulled_lead_id',
        'transferred_to',
        'transferred_by',
        'lead_count',
        'filters_used',
        'transferred_at',
    )
    
    def transferred_to_info(self, obj):
        if obj.transferred_to:
            return f"{obj.transferred_to.get_full_name() or obj.transferred_to.username}"
        return "-"
    transferred_to_info.short_description = 'Transferred To'
    transferred_to_info.admin_order_field = 'transferred_to'
    
    def transferred_by_info(self, obj):
        if obj.transferred_by:
            return f"{obj.transferred_by.get_full_name() or obj.transferred_by.username}"
        return "-"
    transferred_by_info.short_description = 'Transferred By'
    transferred_by_info.admin_order_field = 'transferred_by'
    
    def original_lead_id_display(self, obj):
        return f"#{obj.original_pulled_lead_id}" if obj.original_pulled_lead_id else "-"
    original_lead_id_display.short_description = 'Original ID'
    
    # REMOVE or CHANGE these if you want add/delete permissions
    def has_add_permission(self, request):
        return True   # Change to True if you want to allow adding
    
    def has_delete_permission(self, request, obj=None):
        return True   # Change to True if you want to allow deleting