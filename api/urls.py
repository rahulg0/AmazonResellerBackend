from django.urls import path
from .views import PurchaseOrderView, OrderAPIView,InvoiceFileView

urlpatterns = [
  path('purchase-order', PurchaseOrderView.as_view(), name='purchase-order'),
  path('orders',OrderAPIView.as_view(), name='orders'),
  path('get-invoice',InvoiceFileView.as_view(), name = 'invoice-download' )
]