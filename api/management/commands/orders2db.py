from django.core.management.base import BaseCommand
from api.task import main
import requests
import os
import time
from dotenv import load_dotenv
from datetime import datetime, timedelta, timezone
from api.models import *
from api.serializers import *
import logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
load_dotenv()

class Command(BaseCommand):
    help = "Runs task.py once"

    def handle(self, *args, **kwargs):
        print("Running task.py...")
        main()
        print("Now we wait")

BASE_URL=os.getenv("BASE_URL")
REFRESH_URL=os.getenv("REFRESH_URL")
CLIENT_ID=os.getenv("CLIENT_ID")
CLIENT_SECRET=os.getenv("CLIENT_SECRET")
REFRESH_TOKEN=os.getenv("REFRESH_TOKEN")
MARKETPLACE_ID=os.getenv("MARKETPLACE_ID")

def get_amazon_oauth_token():
    logger.info("taking auth")
    url=REFRESH_URL
    headers={"Content-Type": "application/x-www-form-urlencoded"}
    data={
        "grant_type":"refresh_token",
        "refresh_token":REFRESH_TOKEN,
        "client_id":CLIENT_ID,
        "client_secret":CLIENT_SECRET
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json().get("access_token")


def get_amazon_orders():
    try:
        access_token = get_amazon_oauth_token()
        logger.info("inside getting amazon orders")
        url = BASE_URL + "/orders/v0/orders"
        created_after = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "CreatedAfter": created_after,
            "OrderStatuses": "Shipped",
            "MarketplaceIds": MARKETPLACE_ID
        }
        headers = {
            "accept": "application/json",
            "x-amz-access-token": access_token
        }
        all_orders = []
        request_count = 0
        while True:
            if request_count >= 15:
                logger.info("Burst limit reached, waiting 60 seconds...")
                time.sleep(60)  
                request_count = 0  
            response = requests.get(url, headers=headers, params=params)
            if response.status_code == 429:
                logger.info("Burst limit reached, waiting 60 seconds...")
                time.sleep(60)
                response = requests.get(url, headers=headers, params=params)
            data = response.json().get("payload", {})
            if "Orders" in data:
                all_orders.extend(data["Orders"])
            if "NextToken" in data:
                logger.info("Fetching next page...")
                params = {"NextToken": data["NextToken"]}
                url = BASE_URL + "/orders/v0/orders"
            else:
                break
            request_count += 1
            if request_count >= 20:
                logger.error("Getting New Auth Token")
                access_token=get_amazon_oauth_token()
        return all_orders
    except Exception as e:
        logger.error("Exception in AO: %s", str(e))



def get_details():
    try:
        all_orders = get_amazon_orders()
        access_token = get_amazon_oauth_token()
        logger.info("inside getting details")
        headers = {"x-amz-access-token": access_token}
        logger.info("size of all orders: %s",len(all_orders))
        request_count = 0
        burst_count = 0
        for order in all_orders:
            logger.info("Order Count: %s", request_count)
            a_id = order['AmazonOrderId']
            url = BASE_URL + f'/orders/v0/orders/{a_id}/orderItems'
            if request_count % 100 == 0:
                logger.error("Getting New Auth Token")
                access_token = get_amazon_oauth_token()
                request_count=0
                time.sleep(10)
            resp = requests.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get('payload', {})
                order_item = data.get('OrderItems', {})[0]
                if isinstance(order_item, dict):
                    order.update(order_item)
                else:
                    logger.error(f"Unexpected data format for OrderItems in {a_id}")
            elif resp.status_code == 429:
                logger.info("Burst limit reached, waiting 60 seconds...")
                time.sleep(60)
                resp = requests.get(url, headers=headers)
                if resp.status_code == 200:
                    data = resp.json().get('payload', {})
                    order_item = data.get('OrderItems', {})[0]
                    if isinstance(order_item, dict):
                        order.update(order_item)
                    else:
                        logger.error(f"Unexpected data format for OrderItems in {a_id}")
            else:
                logger.error(f"Failed to fetch details for {a_id}, Status Code: {resp.status_code}")
            request_count += 1
            # if burst_count >= 100:
            #     logger.error("Getting New Auth Token")
            #     access_token = get_amazon_oauth_token()
            #     burst_count=0
        return all_orders
    except Exception as e:
        logger.error("Exception in GD: %s",str(e))


def is_asin_present(asin):
    return PurchaseOrder.objects.filter(asin=asin).exists()

def check_quantity(asin, quantity):
    try:
        item = OrderItem.objects.get(ASIN=asin)        
        if item and item.QuantityLeft < quantity:
            return False        
        item.QuantityLeft -= quantity
        item.save()
        return True
    except OrderItem.DoesNotExist:
        return "ItemNotFound"

def add_order_to_db():
    try:
        orders = get_details()
        logger.info("adding order to db")
        error_orders = []
        serialized_data = []
        existing_error_orders = set(
                ErrorOrders.objects.all()
                .values_list("order_id", flat=True)
            )
        # existing_QuantityNotFound_error_orders = set(
        #     ErrorOrders.objects.filter(reason="QuantityNotFound")
        #     .values_list("order_id", flat=True)
        # )
        # existing_ItemNotFound_error_orders = set(
        #     ErrorOrders.objects.filter(reason="ItemNotFound")
        #     .values_list("order_id", flat=True)
        # )
        orders_data = orders if isinstance(orders, list) else [orders]

        for data in orders_data:
            asin = data.get("ASIN")
            amazon_order_id = data.get("AmazonOrderId")
            if is_asin_present(asin):
                logger.info("asin is present")

                pack_of = int(PurchaseOrder.objects.get(asin=asin).pack_of)
                quantity = data.get("NumberOfItemsShipped", 0) * pack_of
                selling_price = data.get("ItemPrice", {}).get("Amount")

                if not Order.objects.filter(AmazonOrderId=amazon_order_id).exists() and quantity > 0:
                    logger.info("New Order")
                    quantity_status = check_quantity(asin, quantity)

                    if quantity_status is True and selling_price is not None:
                        logger.info("Quantity is available in inventory")
                        logger.info(f"Valid order received for ASIN {asin}")
                        serialized_data.append(data)
                    elif selling_price is None or selling_price == 0 and quantity is True:
                        if amazon_order_id not in existing_error_orders:
                            error_orders.append(ErrorOrders(
                                order_id = amazon_order_id,
                                reason = "ErrorInPriceOrQuantity",
                                data=data
                            ))
                    else:
                        logger.info("Quantity Not available, status == %s", quantity_status)
                        if amazon_order_id not in existing_error_orders:
                            error_orders.append(ErrorOrders(
                                order_id = amazon_order_id,
                                reason = "QuantityNotFound" if  not quantity_status else "ItemNotFound",
                                data=data
                            ))
                elif quantity <= 0:
                    logger.info("Quantity is less than equal to ZERO!!!!")
                else:
                    logger.info("Order already present")
                    ErrorOrders.objects.filter(order_id=amazon_order_id).delete()
            else:
                logger.info("Asin not present: %s", asin)
                if amazon_order_id not in existing_error_orders:
                    error_orders.append(ErrorOrders(
                        order_id = amazon_order_id,
                        reason="ItemNotFound",
                        data=data
                    ))
        if error_orders:
            logger.info("Order in error")
            ErrorOrders.objects.bulk_create(error_orders)
            logger.info(f"Saved {len(error_orders)} error orders")

        serializer = OrderSerializer(data=serialized_data, many=True)
        if serialized_data:
            serializer = OrderSerializer(data=serialized_data, many=True)
            if serializer.is_valid():
                serializer.save()
                valid_order_ids = [order["AmazonOrderId"] for order in serialized_data]
                ErrorOrders.objects.filter(order_id__in=valid_order_ids).delete()
                logger.info(f"Orders saved successfully")

    except Exception as e:
        logger.error("Exception in AOD: %s",str(e))

def main():
    logger.info("pilot.................")
    add_order_to_db()
