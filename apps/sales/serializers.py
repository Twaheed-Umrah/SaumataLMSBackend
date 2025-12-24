# serializers.py
from rest_framework import serializers
from .models import SalesReceipt, DeliveryServiceItem, ReceiptPayment
from django.utils import timezone
from utils.constants import PaymentStatus, DeliveryStatus

class DeliveryServiceItemSerializer(serializers.ModelSerializer):
    """
    Serializer for Delivery Service Item
    """
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to.get_full_name', read_only=True)
    
    class Meta:
        model = DeliveryServiceItem
        fields = [
            'id', 'receipt', 'service_type', 'service_type_display', 'service_name',
            'description', 'status', 'status_display', 'assigned_to',
            'assigned_to_name', 'is_completed', 'completed_at', 'completion_notes',
            'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class ReceiptPaymentSerializer(serializers.ModelSerializer):
    """
    Serializer for Receipt Payment
    """
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    recorded_by_name = serializers.CharField(source='recorded_by.get_full_name', read_only=True)
    
    class Meta:
        model = ReceiptPayment
        fields = [
            'id', 'receipt', 'amount', 'payment_method', 'payment_method_display',
            'payment_reference', 'notes', 'recorded_by', 'recorded_by_name',
            'payment_date', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class SalesReceiptSerializer(serializers.ModelSerializer):
    """
    Serializer for Sales Receipt
    """
    payment_status_display = serializers.CharField(source='get_payment_status_display', read_only=True)
    payment_method_display = serializers.CharField(source='get_payment_method_display', read_only=True)
    created_by_name = serializers.CharField(source='created_by.get_full_name', read_only=True)
    
    # Calculated fields
    progress_percentage = serializers.SerializerMethodField()
    service_items_count = serializers.SerializerMethodField()
    completed_services_count = serializers.SerializerMethodField()
    
    class Meta:
        model = SalesReceipt
        fields = [
            'id', 'receipt_number', 'customer_name', 'customer_email', 
            'customer_phone', 'customer_pan', 'product_name', 'total_budget',
            'paid_amount', 'pending_amount', 'payment_status', 'payment_status_display',
            'description', 'payment_method', 'payment_method_display',
            'payment_reference', 'created_by', 'created_by_name', 'sale_date',
            'is_receipt_issued', 'receipt_issued_date', 'created_at', 'updated_at',
            'progress_percentage', 'service_items_count', 'completed_services_count'
        ]
        read_only_fields = [
            'id', 'receipt_number', 'pending_amount', 'created_by',
            'is_receipt_issued', 'receipt_issued_date', 'created_at', 'updated_at',
            'progress_percentage', 'service_items_count', 'completed_services_count'
        ]
    
    def get_progress_percentage(self, obj):
        """Calculate progress percentage based on paid amount"""
        if obj.total_budget > 0:
            return round((obj.paid_amount / obj.total_budget) * 100, 2)
        return 0
    
    def get_service_items_count(self, obj):
        """Get total service items count"""
        return obj.service_items.count()
    
    def get_completed_services_count(self, obj):
        """Get completed service items count"""
        return obj.service_items.filter(is_completed=True).count()


class SalesReceiptDetailSerializer(SalesReceiptSerializer):
    """
    Detailed serializer for Sales Receipt with related data
    """
    service_items = DeliveryServiceItemSerializer(many=True, read_only=True)
    payments = ReceiptPaymentSerializer(many=True, read_only=True)
    
    class Meta(SalesReceiptSerializer.Meta):
        fields = SalesReceiptSerializer.Meta.fields + ['service_items', 'payments']


class SalesReceiptCreateSerializer(serializers.ModelSerializer):
    """
    Serializer for creating Sales Receipt
    """
    service_items = serializers.ListField(
        child=serializers.DictField(),
        write_only=True,
        required=False,
        default=[]
    )
    
    class Meta:
        model = SalesReceipt
        fields = [
            'customer_name', 'customer_email', 'customer_phone', 'customer_pan',
            'product_name', 'total_budget', 'paid_amount', 'description',
            'payment_method', 'payment_reference', 'sale_date', 'service_items'
        ]
    
    def create(self, validated_data):
        service_items_data = validated_data.pop('service_items', [])
        receipt = SalesReceipt.objects.create(
            **validated_data,
            created_by=self.context['request'].user
        )
        
        # Create default service items based on common requirements
        if not service_items_data:
            # Create default service items
            default_services = [
                {
                    'service_type': 'WEBSITE',
                    'service_name': 'Website Development',
                    'description': 'Custom website development'
                },
                {
                    'service_type': 'LOGO',
                    'service_name': 'Logo Design',
                    'description': 'Company logo design'
                },
                {
                    'service_type': 'SOCIAL_MEDIA',
                    'service_name': 'Social Media Setup',
                    'description': 'Social media accounts creation and setup'
                },
            ]
            
            for service_data in default_services:
                DeliveryServiceItem.objects.create(
                    receipt=receipt,
                    **service_data
                )
        else:
            # Create custom service items
            for item_data in service_items_data:
                DeliveryServiceItem.objects.create(
                    receipt=receipt,
                    **item_data
                )
        
        return receipt


class ReceiptDownloadSerializer(serializers.Serializer):
    """
    Serializer for receipt download
    """
    format = serializers.ChoiceField(
        choices=['pdf', 'html', 'json'],
        default='pdf'
    )
    include_payments = serializers.BooleanField(default=True)
    include_services = serializers.BooleanField(default=True)

class DeliveryServiceItemMiniSerializer(serializers.ModelSerializer):
    service_type_display = serializers.CharField(
        source='get_service_type_display',
        read_only=True
    )
    status_display = serializers.CharField(
        source='get_status_display',
        read_only=True
    )
    assigned_to_name = serializers.SerializerMethodField()

    class Meta:
        model = DeliveryServiceItem
        fields = [
            'id',
            'service_type',
            'service_type_display',
            'service_name',
            'status',
            'status_display',
            'assigned_to_name',
            'is_completed',
            'completed_at'
        ]

    def get_assigned_to_name(self, obj):
        return obj.assigned_to.get_full_name() if obj.assigned_to else None

class SalesReceiptListWithServicesSerializer(serializers.ModelSerializer):
    payment_status_display = serializers.CharField(
        source='get_payment_status_display',
        read_only=True
    )

    services = DeliveryServiceItemMiniSerializer(
        source='service_items',
        many=True,
        read_only=True
    )

    class Meta:
        model = SalesReceipt
        fields = [
            'id',
            'receipt_number',
            'customer_name',
            'customer_email',
            'customer_phone',
            'product_name',

            'total_budget',
            'paid_amount',
            'pending_amount',
            'payment_status',
            'payment_status_display',

            'sale_date',

            # 👇 REQUIRED OUTPUT
            'services'
        ]
class SalesReceiptWithServicesSerializer(serializers.ModelSerializer):
    payment_status_display = serializers.CharField(
        source='get_payment_status_display',
        read_only=True
    )

    services = DeliveryServiceItemMiniSerializer(
        source='service_items',
        many=True,
        read_only=True
    )

    class Meta:
        model = SalesReceipt
        fields = [
            'id',
            'receipt_number',
            'customer_name',
            'customer_email',
            'customer_phone',
            'product_name',

            'total_budget',
            'paid_amount',
            'pending_amount',
            'payment_status',
            'payment_status_display',

            'sale_date',

            'services'
        ]

# serializers.py

class ServiceStatusUpdateSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=DeliveryStatus.CHOICES)
    assigned_to = serializers.IntegerField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
