from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils import timezone
from django.db.models import Q
from .models import ProblemReport


@admin.register(ProblemReport)
class ProblemReportAdmin(admin.ModelAdmin):

    # ================= LIST VIEW =================
    list_display = [
        'title',
        'customer_name',
        'problem_type_display',
        'priority_display',
        'status_display',
        'assigned_to_display',
        'reported_date',
        'due_date',
        'is_overdue_display',
        'row_actions',
    ]

    list_filter = [
        'status',
        'priority',
        'problem_type',
        'is_resolved',
        'reported_date',
        'due_date',
        'assigned_to',
    ]

    search_fields = [
        'title',
        'description',
        'customer_name',
        'customer_email',
        'customer_phone',
        'tour_package',
    ]

    readonly_fields = [
        'reported_date',
        'resolved_date',
        'created_at',
        'updated_at',
        'resolution_time_minutes',
        'communication_history_display',
    ]

    # ================= FIELDSETS =================
    fieldsets = (
        ('Problem Information', {
            'fields': ('title', 'description', 'problem_type', 'priority', 'status')
        }),
        ('Customer Information', {
            'fields': ('customer_name', 'customer_email', 'customer_phone')
        }),
        ('Tour Details', {
            'fields': ('tour_package', 'travel_date'),
            'classes': ('collapse',),
        }),
        ('Assignment & Tracking', {
            'fields': ('assigned_to', 'reported_by', 'reported_date', 'due_date')
        }),
        ('Resolution', {
            'fields': (
                'resolution_notes',
                'resolved_date',
                'resolution_time_minutes',
                'is_resolved',
            )
        }),
        ('Communication History', {
            'fields': ('communication_history_display',),
            'classes': ('collapse',),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )

    # ================= BULK ACTIONS =================
    actions = [
        'mark_as_resolved',
        'assign_to_me',
        'escalate_priority',
        'export_as_csv',
    ]

    # ================= DISPLAY HELPERS =================
    def problem_type_display(self, obj):
        return obj.get_problem_type_display()
    problem_type_display.short_description = 'Type'
    problem_type_display.admin_order_field = 'problem_type'

    def priority_display(self, obj):
        colors = {
            'URGENT': 'red',
            'HIGH': 'orange',
            'MEDIUM': 'blue',
            'LOW': 'green',
        }
        return format_html(
            '<b style="color:{}">{}</b>',
            colors.get(obj.priority, 'black'),
            obj.get_priority_display(),
        )
    priority_display.short_description = 'Priority'

    def status_display(self, obj):
        colors = {
            'PENDING': 'gray',
            'IN_PROGRESS': 'blue',
            'RESOLVED': 'green',
            'ESCALATED': 'orange',
            'CANCELLED': 'red',
        }
        return format_html(
            '<span style="color:{}">{}</span>',
            colors.get(obj.status, 'black'),
            obj.get_status_display(),
        )
    status_display.short_description = 'Status'

    def assigned_to_display(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to else 'Unassigned'
    assigned_to_display.short_description = 'Assigned To'

    def is_overdue_display(self, obj):
        if obj.is_overdue():
            return format_html('<b style="color:red">⚠ OVERDUE</b>')
        return ''
    is_overdue_display.short_description = 'Overdue'

    # ================= ROW ACTION BUTTON =================
    def row_actions(self, obj):
        url = reverse(
            'admin:%s_%s_change' % (obj._meta.app_label, obj._meta.model_name),
            args=[obj.pk],
        )
        return format_html('<a class="button" href="{}">View / Edit</a>', url)
    row_actions.short_description = 'Actions'

    # ================= COMMUNICATION HISTORY =================
    def communication_history_display(self, obj):
        if not obj.communication_history:
            return "No communications yet"

        html = '<div style="max-height:300px;overflow:auto;">'
        for c in obj.communication_history[-10:]:
            html += f"""
            <div style="margin-bottom:6px;padding:6px;border-left:3px solid #2196F3">
                <b>{c.get('user_name', 'System')}</b>
                <small>{c.get('timestamp','')}</small><br>
                {c.get('message','')}
            </div>
            """
        html += '</div>'
        return format_html(html)
    communication_history_display.short_description = 'Communication History'

    # ================= BULK ACTION METHODS =================
    def mark_as_resolved(self, request, queryset):
        count = queryset.update(
            status='RESOLVED',
            is_resolved=True,
            resolved_date=timezone.now(),
        )
        self.message_user(request, f'{count} problem(s) resolved.')

    def assign_to_me(self, request, queryset):
        count = queryset.update(assigned_to=request.user)
        self.message_user(request, f'{count} problem(s) assigned to you.')

    def escalate_priority(self, request, queryset):
        for obj in queryset:
            obj.priority = {
                'LOW': 'MEDIUM',
                'MEDIUM': 'HIGH',
                'HIGH': 'URGENT',
            }.get(obj.priority, obj.priority)
            obj.save()
        self.message_user(request, 'Priority escalated successfully.')

    def export_as_csv(self, request, queryset):
        import csv
        from django.http import HttpResponse

        response = HttpResponse(content_type='text/csv')
        response['Content-Disposition'] = 'attachment; filename=problem_reports.csv'

        writer = csv.writer(response)
        writer.writerow([
            'ID', 'Title', 'Priority', 'Status',
            'Customer', 'Assigned To', 'Due Date',
        ])

        for obj in queryset:
            writer.writerow([
                obj.id,
                obj.title,
                obj.get_priority_display(),
                obj.get_status_display(),
                obj.customer_name,
                obj.assigned_to.get_full_name() if obj.assigned_to else '',
                obj.due_date,
            ])

        return response

    # ================= QUERYSET OPTIMIZATION =================
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('assigned_to', 'reported_by')
