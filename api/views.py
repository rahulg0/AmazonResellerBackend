import os
import time
from datetime import datetime
from django.db.models import Q
from django.conf import settings
from django.shortcuts import render
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .models import PurchaseOrder, Order, OrderItem
from .serializers import PurchaseOrderSerializer, OrderSerializer
import logging
import base64
from decimal import Decimal
from django.db import transaction

#logger configuration
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)


def calculate_profit(selling_price, asin, quantity):
    logger.info(f"Calculating profit for ASIN {asin} with quantity {quantity}")
    with transaction.atomic():
        selling_price = Decimal(str(selling_price))
        orders = PurchaseOrder.objects.filter(asin=asin).select_for_update().order_by('created_at')

        for order in orders:
            if quantity <= 0:
                break

            if order.available_quantity > 0:
                if order.available_quantity >= quantity:
                    order.available_quantity -= quantity
                    order.profit += (selling_price - order.amount_per_unit) * quantity
                    order.profit_percentage = (order.profit / (order.amount_per_unit * quantity)) * 100
                    order.save()
                    quantity = 0
                else:
                    remaining_quantity = order.available_quantity
                    order.available_quantity = 0
                    order.profit += (selling_price - order.amount_per_unit) * remaining_quantity
                    order.profit_percentage = (order.profit / (order.amount_per_unit * remaining_quantity)) * 100
                    order.save()
                    quantity -= remaining_quantity

        if quantity > 0:
            raise ValueError(f"Not enough stock available for ASIN {asin}. Remaining quantity to subtract: {quantity}")

def check_quantity(asin, quantity):
    item = OrderItem.objects.get(ASIN=asin)
    if item.QuantityLeft < quantity:
        return False
    item.QuantityLeft -= quantity
    item.save()
    return True


class PurchaseOrderView(APIView):
    def post(self, request):
        try:
            invoice_file = request.FILES.get('invoice_path', None)
            if not invoice_file:
                return Response({"error": "No invoice file provided"}, status=status.HTTP_400_BAD_REQUEST)
            upload_dir = os.path.join(settings.MEDIA_ROOT, 'invoices')
            os.makedirs(upload_dir, exist_ok=True)
            timestamp = int(time.time())
            file_name = f"{timestamp}_{invoice_file.name}"
            file_path = os.path.join(upload_dir, file_name)
            with open(file_path, 'wb') as f:
                for chunk in invoice_file.chunks():
                    f.write(chunk)
            data = request.data.copy()
            data['invoice_path'] = os.path.relpath(file_path, settings.MEDIA_ROOT)
            print(data)
            if not OrderItem.objects.filter(ASIN=data['asin']).exists():
                OrderItem.objects.create(
                    ASIN=data['asin'],
                    QuantityLeft=data['quantity'],
                )
            else:
                item = OrderItem.objects.get(ASIN=data['asin'])
                item.QuantityLeft += data['quantity']
                item.save()
            serializer = PurchaseOrderSerializer(data=data)
            if serializer.is_valid():
                serializer.save()
                return Response({"message": "Data created successfully"}, status=status.HTTP_201_CREATED)
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            logger.error(e)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def get(self, request):
        try:
            order = request.query_params.get('order', 'created_at')
            sort = request.query_params.get('sort', None)
            if sort == 'asc':
                purchase_orders = PurchaseOrder.objects.all().order_by(order)
            else:
                purchase_orders = PurchaseOrder.objects.all().order_by(f'-{order}')
            serializer = PurchaseOrderSerializer(purchase_orders, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(e)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request):
        try:
            order_uuid = request.query_params.get('order_uuid', None)
            if not order_uuid:
                return Response({"error": "No order uuid provided"}, status=status.HTTP_400_BAD_REQUEST)
            purchase_order = PurchaseOrder.objects.get(order_uuid=order_uuid)
            purchase_order.delete()
            return Response({"message": "Data deleted successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(e)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class OrderAPIView(APIView):
    def post(self, request):
        try:
            invalid_orders = []
            serialized_data = []
            
            orders_data = request.data if isinstance(request.data, list) else [request.data]

            for data in orders_data:
                asin = data.get("ASIN")
                quantity = data.get("NumberOfItemsShipped", 0)
                selling_price = data.get("ItemPrice", {}).get("Amount")
                print(quantity,asin)

                if check_quantity(asin, quantity):
                    logger.info(f"Valid order received for ASIN {asin}")
                    serialized_data.append(data)
                    if selling_price is not None:
                        calculate_profit(
                            selling_price=float(selling_price),
                            asin=asin,
                            quantity=quantity,
                        )
                    else:
                        logger.error(f"Invalid selling price for ASIN {asin}")
                        invalid_orders.append(data.get("AmazonOrderId", "Unknown"))
                else:
                    logger.error(f"Invalid quantity for ASIN {asin}")
                    invalid_orders.append(data.get("AmazonOrderId", "Unknown"))

            # Serialize and save valid orders
            serializer = OrderSerializer(data=serialized_data, many=True)
            if serializer.is_valid():
                serializer.save()
                logger.info(f"Orders saved successfully")

                # for order, data in zip(orders, serialized_data):
                #     selling_price = data.get("ItemPrice", {}).get("Amount")
                #     if selling_price is not None:
                #         calculate_profit(
                #             selling_price=float(selling_price),
                #             asin=order.asin,
                #             quantity=order.quantity,
                #         )

                return Response(
                    {
                        "message": "Data created successfully",
                        "InvalidAmazonOrderId": invalid_orders,
                    },
                    status=status.HTTP_201_CREATED,
                )
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        except Exception as e:
            logger.error(e)
            return Response(
                {"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


    def get(self, request):
        try:
            order = request.query_params.get('order', 'PurchaseDate')
            sort = request.query_params.get('sort', 'asc')
            start_date = request.query_params.get('start_date', None)
            end_date = request.query_params.get('end_date', None)
            query_conditions = Q()
            if start_date and end_date:
                try:
                    start_date = datetime.strptime(start_date, '%Y-%m-%d')
                    end_date = datetime.strptime(end_date, '%Y-%m-%d')
                    query_conditions &= Q(PurchaseDate__gte=start_date) & Q(PurchaseDate__lte=end_date)
                except ValueError:
                    return Response({"error": "Invalid date format. Use 'YYYY-MM-DD'."}, status=status.HTTP_400_BAD_REQUEST)
            orders_query = Order.objects.filter(query_conditions)
            if sort == 'desc':
                orders_query = orders_query.order_by(f'-{order}')
            else:
                orders_query = orders_query.order_by(order)
            orders = orders_query.all()
            serializer = OrderSerializer(orders, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            logger.error(f"Error fetching orders: {e}")
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request):
        try:
            AmazonOrderId = request.query_params.get('AmazonOrderId', None)
            if not AmazonOrderId:
                return Response({"error": "No AmazonOrderId provided"}, status=status.HTTP_400_BAD_REQUEST)
            order = Order.objects.get(AmazonOrderId=AmazonOrderId)
            order.delete()
            return Response({"message": "Data deleted successfully"}, status=status.HTTP_200_OK)
        except Exception as e:
            logger.error(e)
            return Response({"error": "Internal server error"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)