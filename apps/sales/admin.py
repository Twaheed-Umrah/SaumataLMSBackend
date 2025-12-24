# admin.py
from django.contrib import admin
from .models import SalesReceipt, DeliveryServiceItem, ReceiptPayment


class DeliveryServiceItemInline(admin.TabularInline):
    model = DeliveryServiceItem
    extra = 1
    fields = ['service_type', 'service_name', 'status', 'assigned_to', 'is_completed']
    readonly_fields = ['created_at', 'updated_at']


class ReceiptPaymentInline(admin.TabularInline):
    model = ReceiptPayment
    extra = 0
    readonly_fields = ['created_at']


@admin.register(SalesReceipt)
class SalesReceiptAdmin(admin.ModelAdmin):
    list_display = [
        'receipt_number', 'customer_name', 'product_name',
        'total_budget', 'paid_amount', 'pending_amount',
        'payment_status', 'is_receipt_issued', 'sale_date'
    ]
    list_filter = ['payment_status', 'is_receipt_issued', 'sale_date', 'payment_method']
    search_fields = [
        'receipt_number', 'customer_name', 'customer_email',
        'customer_phone', 'product_name'
    ]
    readonly_fields = [
        'receipt_number', 'pending_amount', 'created_at',
        'updated_at', 'receipt_issued_date'
    ]
    inlines = [DeliveryServiceItemInline, ReceiptPaymentInline]
    
    fieldsets = (
        ('Customer Information', {
            'fields': (
                'customer_name', 'customer_email', 'customer_phone',
                'customer_pan'
            )
        }),
        ('Product Information', {
            'fields': ('product_name', 'description')
        }),
        ('Financial Information', {
            'fields': (
                'receipt_number', 'total_budget', 'paid_amount',
                'pending_amount', 'payment_status', 'payment_method',
                'payment_reference'
            )
        }),
        ('Receipt Status', {
            'fields': ('is_receipt_issued', 'receipt_issued_date', 'sale_date')
        }),
        ('System Information', {
            'fields': ('created_by', 'created_at', 'updated_at'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        if not change:  # If creating a new object
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(DeliveryServiceItem)
class DeliveryServiceItemAdmin(admin.ModelAdmin):
    list_display = [
        'service_name', 'receipt', 'get_service_type_display',
        'status', 'assigned_to', 'is_completed', 'created_at'
    ]
    list_filter = ['service_type', 'status', 'is_completed', 'created_at']
    search_fields = ['service_name', 'receipt__receipt_number', 'receipt__customer_name']
    readonly_fields = ['created_at', 'updated_at']
    
    def get_receipt_number(self, obj):
        return obj.receipt.receipt_number
    get_receipt_number.short_description = 'Receipt Number'
    
    def get_customer_name(self, obj):
        return obj.receipt.customer_name
    get_customer_name.short_description = 'Customer Name'


@admin.register(ReceiptPayment)
class ReceiptPaymentAdmin(admin.ModelAdmin):
    list_display = [
        'receipt', 'amount', 'get_payment_method_display',
        'payment_date', 'recorded_by', 'created_at'
    ]
    list_filter = ['payment_method', 'payment_date']
    search_fields = ['receipt__receipt_number', 'receipt__customer_name', 'payment_reference']
    readonly_fields = ['created_at']
    
    def get_receipt_number(self, obj):
        return obj.receipt.receipt_number
    get_receipt_number.short_description = 'Receipt Number'