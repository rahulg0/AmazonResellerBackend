import requests
from celery import shared_task
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

BASE_URL=os.getenv("BASE_URL")
REFRESH_URL=os.getenv("REFRESH_URL")
CLIENT_ID=os.getenv("CLIENT_ID")
CLIENT_SECRET=os.getenv("CLIENT_SECRET")
REFRESH_TOKEN=os.getenv("REFRESH_TOKEN")
MARKETPLACE_ID=os.getenv("MARKETPLACE_ID")


def get_amazon_oauth_token(refresh_token,client_id,client_secret):
    print("taking auth")
    url=REFRESH_URL
    headers={"Content-Type": "application/x-www-form-urlencoded"}
    data={
        "grant_type":"refresh_token",
        "refresh_token":refresh_token,
        "client_id":client_id,
        "client_secret":client_secret
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json().get("access_token")


def get_amazon_orders(access_token):
    try:
        print("inside getting amazon orders")
        url = BASE_URL + "/orders/v0/orders"
        created_after = (datetime.now(timezone.utc) - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
        params = {
            "CreatedAfter": created_after,
            "OrderStatus": "Shipped",
            "MarketplaceIds": MARKETPLACE_ID
        }
        headers = {
            "accept": "application/json",
            "x-amz-access-token": access_token
        }
        all_orders = []
        request_count = 0
        while True:
            if request_count >= 20:  
                print("Burst limit reached, waiting 60 seconds...")
                time.sleep(60)  
                request_count = 0  
            response = requests.get(url, headers=headers, params=params)
            data = response.json().get("payload", {})
            print(data)
            if "Orders" in data:
                all_orders.extend(data["Orders"])
            if "NextToken" in data:
                print("Fetching next page...")
                params = {"NextToken": data["NextToken"]}
                url = BASE_URL + "/orders/v0/orders"
            else:
                break
            request_count += 1
        return all_orders
    except Exception as e:
        print("Exception in AO:", str(e))


def get_details(access_token):
    try:
        all_orders = get_amazon_orders(access_token)
        print("inside getting details")
        headers = {"x-amz-access-token": access_token}
        print("size of all orders: ",len(all_orders))
        request_count = 0
        for order in all_orders:
            a_id = order['AmazonOrderId']
            url = BASE_URL + f'/orders/v0/orders/{a_id}/orderItems'
            if request_count >= 30:
                print("Burst limit reached, waiting 2 seconds per request...")
                time.sleep(2)
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
        return all_orders
    except Exception as e:
        print("Exception in GD: ",str(e))

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

def add_order_to_db(access_token):
    try:
        orders = get_details(access_token)
        print("adding order to db")
        error_orders = []
        serialized_data = []

        orders_data = orders if isinstance(orders, list) else [orders]

        for data in orders_data:
            print(data)
            asin = data.get("ASIN")

            if is_asin_present(asin):
                amazon_order_id = data.get("AmazonOrderId")

                pack_of = int(PurchaseOrder.objects.get(asin=asin).pack_of)
                quantity = data.get("NumberOfItemsShipped", 0) * pack_of
                selling_price = data.get("ItemPrice", {}).get("Amount")

                if not Order.objects.filter(AmazonOrderId=amazon_order_id).exists():
                    quantity_status = check_quantity(asin, quantity)

                    if quantity_status is True and selling_price is not None:
                        logger.info(f"Valid order received for ASIN {asin}")
                        serialized_data.append(data)
                    else:
                        error_orders.append(ErrorOrders(
                            id_type="AmazonOrderId" if quantity_status != "ItemNotFound" else "ASIN",
                            id_value=amazon_order_id if quantity_status != "ItemNotFound" else asin,
                            data=data
                        ))
            else:
                error_orders.append(ErrorOrders(
                    id_type="ASIN",
                    id_value=asin,
                    data=data
                ))

        serializer = OrderSerializer(data=serialized_data, many=True)
        if serializer.is_valid():
            serializer.save()
            logger.info("Orders saved successfully")

        if error_orders:
            ErrorOrders.objects.bulk_create(error_orders)
            logger.info(f"Saved {len(error_orders)} error orders")
    except Exception as e:
        print("Exception in AOD: ",str(e))

@shared_task
def main():
    print("pilot.................")
    access_token=get_amazon_oauth_token(REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET)
    add_order_to_db(access_token)
