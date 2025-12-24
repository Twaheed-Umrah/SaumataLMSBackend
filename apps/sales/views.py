# views.py
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from django.utils import timezone
from django.db.models import Sum, Q
from django.http import HttpResponse
from django.template.loader import render_to_string
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated
from django.utils.decorators import method_decorator
from django.views.decorators.cache import cache_page
from django.db.models import Count, Sum, Q
from django.utils import timezone
from datetime import timedelta
import logging
from weasyprint import HTML, CSS
from weasyprint.text.fonts import FontConfiguration
from django.conf import settings
from django.db import transaction
from utils.constants import DeliveryStatus
import json
import io
logger = logging.getLogger(__name__)
from .models import SalesReceipt, DeliveryServiceItem, ReceiptPayment
from .serializers import (
    SalesReceiptSerializer, SalesReceiptDetailSerializer,
    SalesReceiptCreateSerializer, DeliveryServiceItemSerializer,
    ReceiptPaymentSerializer, ReceiptDownloadSerializer,SalesReceiptListWithServicesSerializer,SalesReceiptWithServicesSerializer,
    ServiceStatusUpdateSerializer
)
from utils.constants import PaymentStatus, DeliveryStatus
from utils.permissions import IsTeamLeaderOrSuperAdmin
from utils.response import success_response, error_response, created_response
from .media_utils import get_company_context

class SalesReceiptViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Sales Receipt operations
    """
    queryset = SalesReceipt.objects.all()
    serializer_class = SalesReceiptSerializer
    permission_classes = [IsTeamLeaderOrSuperAdmin]
    filterset_fields = ['payment_status', 'sale_date', 'is_receipt_issued']
    search_fields = [
        'receipt_number', 'customer_name', 'customer_email',
        'customer_phone', 'product_name'
    ]
    ordering_fields = ['created_at', 'sale_date', 'total_budget']
    
    def get_serializer_class(self):
        if self.action == 'list':
            return SalesReceiptListWithServicesSerializer 
        if self.action == 'retrieve':
            return SalesReceiptDetailSerializer
        elif self.action == 'create':
            return SalesReceiptCreateSerializer
        return SalesReceiptSerializer
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by service status if provided
        service_status = self.request.query_params.get('service_status')
        if service_status:
            queryset = queryset.filter(
                service_items__status=service_status
            ).distinct()
        
        return queryset
    
    def list(self, request):
        """List all sales receipts"""
        queryset = self.filter_queryset(self.get_queryset())
        
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)
        
        serializer = self.get_serializer(queryset, many=True)
        return success_response(serializer.data, "Sales receipts retrieved successfully")
    
    def create(self, request):
        """Create a new sales receipt"""
        serializer = self.get_serializer(data=request.data)
        if serializer.is_valid():
            receipt = serializer.save()
            
            return created_response(
                SalesReceiptDetailSerializer(receipt).data,
                "Sales receipt created successfully"
            )
        return error_response("Validation failed", serializer.errors)
    
    @action(detail=True, methods=['post'])
    def add_payment(self, request, pk=None):
        """Add a payment to receipt"""
        try:
            receipt = self.get_object()
            serializer = ReceiptPaymentSerializer(data=request.data)
            
            if not serializer.is_valid():
                return error_response("Validation failed", serializer.errors)
            
            # Create payment
            payment = serializer.save(
                receipt=receipt,
                recorded_by=request.user
            )
            
            # Update receipt paid amount
            receipt.paid_amount += payment.amount
            receipt.payment_method = payment.payment_method
            receipt.payment_reference = payment.payment_reference
            receipt.save()
            
            return created_response(
                ReceiptPaymentSerializer(payment).data,
                "Payment added successfully"
            )
        except SalesReceipt.DoesNotExist:
            return error_response("Sales receipt not found", status_code=status.HTTP_404_NOT_FOUND)
    
    @action(detail=True, methods=['post'], url_path='update_service_status')
    def update_service_status(self, request, pk=None):
        """
        Bulk update service items status for a receipt
        """
        receipt = self.get_object()
        services_data = request.data.get('services')

        if not services_data:
            return error_response("Services data is required")

        serializer = ServiceStatusUpdateSerializer(data=services_data, many=True)
        if not serializer.is_valid():
            return error_response("Validation failed", serializer.errors)

        updated_services = []
        errors = []

        with transaction.atomic():
            for service_data in serializer.validated_data:
                try:
                    service_item = receipt.service_items.get(id=service_data['id'])
                    service_item.status = service_data['status']

                    # Optional: assign user if provided
                    if 'assigned_to' in service_data:
                        service_item.assigned_to_id = service_data['assigned_to']

                    # Mark completed if status is COMPLETED
                    if service_data['status'] == DeliveryStatus.COMPLETED:
                        service_item.is_completed = True
                        service_item.completed_at = timezone.now()
                        service_item.completion_notes = service_data.get('notes', '')

                    service_item.save()
                    updated_services.append(service_item)

                except DeliveryServiceItem.DoesNotExist:
                    errors.append({
                        "service_id": service_data['id'],
                        "error": "Service item not found for this receipt"
                    })

        return success_response(
            {
                "updated_count": len(updated_services),
                "errors": errors,
                "services": DeliveryServiceItemSerializer(updated_services, many=True).data
            },
            "Services updated successfully"
        )
    @action(detail=True, methods=['post'])
    def issue_receipt(self, request, pk=None):
        """Mark receipt as issued"""
        try:
            receipt = self.get_object()
            receipt.issue_receipt()
            
            return success_response(
                self.get_serializer(receipt).data,
                "Receipt issued successfully"
            )
        except SalesReceipt.DoesNotExist:
            return error_response("Sales receipt not found")
    
    @action(detail=True, methods=['get', 'post'])
    def download(self, request, pk=None):
        """Download receipt - PRODUCTION READY with media folder"""
        try:
            receipt = self.get_object()
        
            # Get format from request
            if request.method == 'POST':
                serializer = ReceiptDownloadSerializer(data=request.data)
                if not serializer.is_valid():
                    return error_response("Invalid format", serializer.errors)
                data = serializer.validated_data
            else:
                data = {'format': 'pdf', 'include_payments': True, 'include_services': True}
        
            # Create base context
            context = {
                'receipt': receipt,
                'payments': receipt.payments.all() if data['include_payments'] else [],
                'services': receipt.service_items.all() if data['include_services'] else [],
                'issued_date': timezone.now(),
            }
            
            # ADD COMPANY INFO FROM MEDIA
            context.update(get_company_context())
            
            # Generate response based on format
            format_type = data['format']
            if format_type == 'pdf':
                return self._generate_pdf_receipt(context, receipt.receipt_number)
            elif format_type == 'html':
                return self._generate_html_receipt(context)
            else:  # json
                return self._generate_json_receipt(context)
            
        except SalesReceipt.DoesNotExist:
            return error_response("Sales receipt not found")

    def _generate_pdf_receipt(self, context, receipt_number):
          """Generate PDF using WeasyPrint (production ready)"""

          context.update(get_company_context())
      
          html_string = render_to_string(
              'receipts/receipt_template.html',
              context
          )
      
          response = HttpResponse(content_type='application/pdf')
          response['Content-Disposition'] = (
        f'attachment; filename="receipt_{receipt_number}.pdf"'
          )

          font_config = FontConfiguration()

          HTML(
              string=html_string,
              base_url=settings.BASE_DIR
          ).write_pdf(
              response,
              font_config=font_config,
              stylesheets=[
                  CSS(
                      string="""
                      @page {
                          size: A4;
                          margin: 20mm;
                      }
                      body {
                    -webkit-print-color-adjust: exact;
                          print-color-adjust: exact;
                      }
                      """
                  )
              ]
          )

          return response

    
    def _generate_html_receipt(self, context):
        """Generate HTML receipt"""
        html_string = render_to_string('receipts/receipt_template.html', context)
        response = HttpResponse(html_string, content_type='text/html')
        response['Content-Disposition'] = 'attachment; filename="receipt.html"'
        return response
    
    def _generate_json_receipt(self, context):
        """Generate JSON receipt"""
        data = {
            'receipt': SalesReceiptDetailSerializer(context['receipt']).data,
            'payments': ReceiptPaymentSerializer(context['payments'], many=True).data if context['payments'] else [],
            'services': DeliveryServiceItemSerializer(context['services'], many=True).data if context['services'] else [],
            'issued_date': context['issued_date'].isoformat(),
            'company_info': {
                'name': context['company_name'],
                'address': context['company_address'],
                'phone': context['company_phone'],
                'email': context['company_email'],
            }
        }
        
        response = HttpResponse(
            json.dumps(data, indent=2),
            content_type='application/json'
        )
        response['Content-Disposition'] = 'attachment; filename="receipt.json"'
        return response
    
    @action(detail=False, methods=['get'])
    def summary(self, request):
        """Get sales summary"""
        total_sales = SalesReceipt.objects.aggregate(
            total_budget=Sum('total_budget'),
            total_paid=Sum('paid_amount')
        )
        
        # Calculate pending amount
        total_pending = (total_sales['total_budget'] or 0) - (total_sales['total_paid'] or 0)
        
        # Service status summary
        service_status_summary = {}
        for status_choice in DeliveryStatus.CHOICES:
            status_code = status_choice[0]
            count = DeliveryServiceItem.objects.filter(status=status_code).count()
            service_status_summary[status_code] = count
        
        data = {
            'total_budget': total_sales['total_budget'] or 0,
            'total_paid': total_sales['total_paid'] or 0,
            'total_pending': total_pending,
            'total_receipts': SalesReceipt.objects.count(),
            'issued_receipts': SalesReceipt.objects.filter(is_receipt_issued=True).count(),
            'service_status_summary': service_status_summary
        }
        
        return success_response(data, "Sales summary retrieved successfully")


class DeliveryServiceItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Delivery Service Item operations
    """
    queryset = DeliveryServiceItem.objects.all()
    serializer_class = DeliveryServiceItemSerializer
    permission_classes = [IsTeamLeaderOrSuperAdmin]
    filterset_fields = ['status', 'service_type', 'is_completed', 'assigned_to']
    search_fields = ['service_name', 'receipt__receipt_number', 'receipt__customer_name']
    
    def get_queryset(self):
        queryset = super().get_queryset()
        
        # Filter by receipt if provided
        receipt_id = self.request.query_params.get('receipt_id')
        if receipt_id:
            queryset = queryset.filter(receipt_id=receipt_id)
        
        return queryset
    
    @action(detail=True, methods=['post'])
    def assign(self, request, pk=None):
        """Assign service item to user"""
        try:
            item = self.get_object()
            user_id = request.data.get('assigned_to')
            
            if user_id:
                from django.contrib.auth import get_user_model
                User = get_user_model()
                try:
                    user = User.objects.get(id=user_id)
                    item.assigned_to = user
                    item.save()
                except User.DoesNotExist:
                    return error_response("User not found")
            
            return success_response(
                self.get_serializer(item).data,
                "Service item assigned successfully"
            )
        except DeliveryServiceItem.DoesNotExist:
            return error_response("Service item not found")
    
    @action(detail=False, methods=['get'])
    def by_service_type(self, request):
        """Get service items grouped by service type"""
        service_type = request.query_params.get('type')
        
        if service_type:
            items = self.get_queryset().filter(service_type=service_type)
        else:
            items = self.get_queryset()
        
        # Group by status
        grouped_data = {}
        for item in items:
            status_display = item.get_status_display()
            if status_display not in grouped_data:
                grouped_data[status_display] = []
            
            serializer = self.get_serializer(item)
            grouped_data[status_display].append(serializer.data)
        
        return success_response(grouped_data, "Service items retrieved by type")


class ReceiptPaymentViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Receipt Payment operations
    """
    queryset = ReceiptPayment.objects.all()
    serializer_class = ReceiptPaymentSerializer
    permission_classes = [IsTeamLeaderOrSuperAdmin]
    filterset_fields = ['payment_method', 'payment_date']
    search_fields = ['receipt__receipt_number', 'receipt__customer_name', 'payment_reference']
# Add this to views.py for your specific frontend needs

class SimpleSalesStatsAPIView(APIView):
    """
    Simplified stats endpoint matching frontend expectations
    """
    permission_classes = [IsTeamLeaderOrSuperAdmin]
    
    @method_decorator(cache_page(60))  # Cache for 1 minute
    def get(self, request, *args, **kwargs):
        """
        Get simplified stats matching frontend structure
        """
        try:
            # Import your constants here if needed
            from utils.constants import PaymentStatus
            
            # Total stats with a single query for efficiency
            stats = SalesReceipt.objects.aggregate(
                total_revenue=Sum('total_budget'),
                total_paid_amount=Sum('paid_amount'),
                total_receipts=Count('id'),
                paid_count=Count('id', filter=Q(payment_status=PaymentStatus.COMPLETED)),
                pending_count=Count('id', filter=Q(
                    Q(payment_status=PaymentStatus.PENDING) | 
                    Q(payment_status=PaymentStatus.PARTIAL)
                ))
            )
            
            # Calculate additional metrics
            total_pending_amount = (stats['total_revenue'] or 0) - (stats['total_paid_amount'] or 0)
            
            # Today's stats for real-time insights
            today = timezone.now().date()
            today_stats = SalesReceipt.objects.filter(sale_date=today).aggregate(
                today_revenue=Sum('total_budget'),
                today_receipts=Count('id')
            )
            
            # This week's stats (Monday to today)
            week_start = today - timedelta(days=today.weekday())
            week_stats = SalesReceipt.objects.filter(
                sale_date__gte=week_start
            ).aggregate(
                week_revenue=Sum('total_budget'),
                week_receipts=Count('id')
            )
            
            # Format response exactly as frontend expects
            data = {
                # Core stats for dashboard cards
                'total': stats['total_receipts'] or 0,
                'revenue': float(stats['total_revenue'] or 0),
                'paid': stats['paid_count'] or 0,           # Count of paid receipts
                'pending': stats['pending_count'] or 0,     # Count of pending receipts
                'cancelled': 0,  # Add if you implement cancelled status
                
                # Additional metrics that might be useful
                'amounts': {
                    'total_collected': float(stats['total_paid_amount'] or 0),
                    'total_pending': float(total_pending_amount),
                    'avg_order_value': float(
                        (stats['total_revenue'] or 0) / (stats['total_receipts'] or 1)
                    )
                },
                
                # Real-time insights
                'today': {
                    'revenue': float(today_stats['today_revenue'] or 0),
                    'receipts': today_stats['today_receipts'] or 0
                },
                
                'week': {
                    'revenue': float(week_stats['week_revenue'] or 0),
                    'receipts': week_stats['week_receipts'] or 0
                },
                
                # Service delivery stats (if you want to show service completion)
                'services': {
                    'total': DeliveryServiceItem.objects.count(),
                    'completed': DeliveryServiceItem.objects.filter(is_completed=True).count(),
                    'pending': DeliveryServiceItem.objects.filter(is_completed=False).count()
                },
                
                # Metadata
                'updated_at': timezone.now().isoformat(),
                'cache_ttl': 60  # Cache time in seconds
            }
            
            # Use your existing success_response format
            return success_response(data, "Statistics retrieved successfully")
            
        except Exception as e:
            logger.error(f"Error fetching sales stats: {str(e)}", exc_info=True)
            # Use your existing error_response format
            return error_response(
                "Failed to fetch statistics",
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
        

# views.py

class DeliveryServiceReceiptListAPIView(generics.ListAPIView):
    """
    List receipts with their delivery services
    """
    serializer_class = SalesReceiptWithServicesSerializer
    permission_classes = [IsTeamLeaderOrSuperAdmin]

    def get_queryset(self):
        queryset = SalesReceipt.objects.prefetch_related(
            'service_items',
            'service_items__assigned_to'
        )

        # Optional filters
        service_status = self.request.query_params.get('service_status')
        if service_status:
            queryset = queryset.filter(
                service_items__status=service_status
            )

        assigned_to = self.request.query_params.get('assigned_to')
        if assigned_to:
            queryset = queryset.filter(
                service_items__assigned_to_id=assigned_to
            )

        return queryset.distinct()
