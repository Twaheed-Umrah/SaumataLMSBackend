from django.urls import path
from .views import (
    SalesReceiptViewSet,
    DeliveryServiceItemViewSet,
    ReceiptPaymentViewSet,
    SimpleSalesStatsAPIView,
    DeliveryServiceReceiptListAPIView
)

# Sales Receipt APIs
sales_receipt_list = SalesReceiptViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

sales_receipt_detail = SalesReceiptViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'delete': 'destroy'
})

add_payment = SalesReceiptViewSet.as_view({
    'post': 'add_payment'
})

update_service_status = SalesReceiptViewSet.as_view({
    'post': 'update_service_status'
})

issue_receipt = SalesReceiptViewSet.as_view({
    'post': 'issue_receipt'
})

download_receipt = SalesReceiptViewSet.as_view({
    'get': 'download',
    'post': 'download'
})

sales_summary = SalesReceiptViewSet.as_view({
    'get': 'summary'
})


# Delivery Service APIs
delivery_service_list = DeliveryServiceItemViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

delivery_service_detail = DeliveryServiceItemViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'delete': 'destroy'
})

assign_service = DeliveryServiceItemViewSet.as_view({
    'post': 'assign'
})

service_by_type = DeliveryServiceItemViewSet.as_view({
    'get': 'by_service_type'
})


# Receipt Payment APIs
payment_list = ReceiptPaymentViewSet.as_view({
    'get': 'list',
    'post': 'create'
})

payment_detail = ReceiptPaymentViewSet.as_view({
    'get': 'retrieve',
    'patch': 'partial_update',
    'delete': 'destroy'
})


urlpatterns = [
    # Sales Receipts
    path('receipts/', sales_receipt_list),
    path('receipts/<int:pk>/', sales_receipt_detail),
    path('receipts/<int:pk>/add-payment/', add_payment),
    path('receipts/<int:pk>/update-service-status/', update_service_status),
    path('receipts/<int:pk>/issue-receipt/', issue_receipt),
    path('receipts/<int:pk>/download/', download_receipt),
    path('receipts/summary/', sales_summary),
    path('stats/', SimpleSalesStatsAPIView.as_view(), name='sales-stats'),
    # Delivery Services
    path('delivery-services/', delivery_service_list),
    path('delivery-services/<int:pk>/', delivery_service_detail),
    path('delivery-services/<int:pk>/assign/', assign_service),
    path('delivery-services/by-service-type/', service_by_type),

    # Receipt Payments
    path('receipt-payments/', payment_list),
    path('receipt-payments/<int:pk>/', payment_detail),
    path(
        'delivery-services/receipts/',
        DeliveryServiceReceiptListAPIView.as_view(),
        name='delivery-services-receipts'
    ),
]
