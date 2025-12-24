from django.contrib import admin
from .models import Lead, LeadActivity, FollowUp


class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    readonly_fields = ['created_at']


class FollowUpInline(admin.TabularInline):
    model = FollowUp
    extra = 0


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ['name', 'phone', 'lead_type', 'status', 'assigned_to', 'created_at']
    list_filter = ['lead_type', 'status', 'created_at']
    search_fields = ['name', 'email', 'phone', 'company']
    readonly_fields = ['created_at', 'updated_at', 'converted_at']
    inlines = [LeadActivityInline, FollowUpInline]
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'email', 'phone', 'company', 'city', 'state')
        }),
        ('Lead Details', {
            'fields': ('lead_type', 'status', 'notes')
        }),
        ('Assignment', {
            'fields': ('assigned_to', 'uploaded_by')
        }),
        ('Conversion', {
            'fields': ('original_type', 'converted_by', 'converted_at')
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at')
        }),
    )


@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ['lead', 'user', 'activity_type', 'created_at']
    list_filter = ['activity_type', 'created_at']
    search_fields = ['lead__name', 'description']
    readonly_fields = ['created_at']


@admin.register(FollowUp)
class FollowUpAdmin(admin.ModelAdmin):
    list_display = ['lead', 'assigned_to', 'scheduled_date', 'completed', 'created_at']
    list_filter = ['completed', 'scheduled_date']
    search_fields = ['lead__name', 'notes']
    readonly_fields = ['created_at', 'updated_at']