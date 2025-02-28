from django.urls import path
from .views import *

urlpatterns = [
  path('purchase-order', PurchaseOrderView.as_view(), name='purchase-order'),
  path('orders',OrderAPIView.as_view(), name='orders'),
  path('get-invoice',InvoiceFileView.as_view(), name = 'invoice-download' ),
  path('purchase-orders/year-wise/', year_wise_purchase_orders, name='year-wise-purchase-orders'),
  path('orders/month-wise-profit/', month_wise_profit, name='month-wise-profit'),

]