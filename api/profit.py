import requests
import os
import time
import json
from decimal import Decimal
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
    logger.info("taking auth")
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

def get_data(access_token, a_id, retries=3, retry_delay=2):
    url = f"{BASE_URL}/finances/v0/orders/{a_id}/financialEvents"
    headers = {
        "x-amz-access-token": access_token
    }
    for attempt in range(retries):
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            data = response.json().get("payload", {}).get("FinancialEvents", [])
            return data if data else None
        if response.status_code == 429:
            if attempt < retries - 1:
                time.sleep(retry_delay)
            else:
                raise Exception("Rate limit exceeded, retries exhausted.")
        else:
            response.raise_for_status()
    return None

def update_profit():
    access_token = get_amazon_oauth_token(REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET)
    all_orders = Order.objects.filter(have_profit=False).values_list("AmazonOrderId", "ASIN", "QuantityShipped").iterator()
    for orders in all_orders:
        amazon_order_id, asin, quantity = orders
        pos = PurchaseOrder.objects.filter(asin=asin).order_by('created_at')
        COG = 0
        remaining_quantity = quantity
        used_pos = []
        for po in pos:
            if remaining_quantity <= 0:
                break
            if po.available_quantity == 0:
                continue
            used_quantity = min(remaining_quantity, po.available_quantity)
            COG += used_quantity * po.amount_per_unit
            remaining_quantity -= used_quantity
            used_pos.append((po, used_quantity))
        if remaining_quantity > 0:
            continue
        data = get_data(access_token, amazon_order_id)
        if 'ShipmentEventList' in data:
            shipment_events = data['ShipmentEventList']
            if shipment_events:  # Ensure it's not empty
                shipment = shipment_events[0]  # Get first shipment event
                shipment_items = shipment.get('ShipmentItemList', [])  # Get ShipmentItemList safely
            else:
                logger.info("No Shipment")
                continue
            logger.info("Have shipment events")
        else:
            logger.info("No shipment")
            continue
        shipment = shipment_items[0]
        # print(json.dumps(shipment, indent=3))
        principal,shipping_charge,fba_fee,commission,promotion_discount = 0,0,0,0,0
        final_profit=0
        try:
            itemchargeList = shipment['ItemChargeList'] if 'ItemChargeList' in shipment else []
            ItemFeeList = shipment['ItemFeeList'] if 'ItemFeeList' in shipment else []
            PromotionList = shipment['PromotionList'] if 'PromotionList' in shipment else []
        except KeyError as e:
            logger.error(f"KeyError: {e} not found in shipment")
        if itemchargeList:
            principal = next((charge["ChargeAmount"]["CurrencyAmount"] for charge in itemchargeList if charge["ChargeType"] == "Principal"), 0)
            shipping_charge = next((charge["ChargeAmount"]["CurrencyAmount"] for charge in itemchargeList if charge["ChargeType"] == "ShippingCharge"), 0)
        if ItemFeeList:
            fba_fee = next((fee["FeeAmount"]["CurrencyAmount"] for fee in ItemFeeList if fee["FeeType"] == "FBAPerUnitFulfillmentFee"), 0)
            commission = next((fee["FeeAmount"]["CurrencyAmount"] for fee in ItemFeeList if fee["FeeType"] == "Commission"), 0)
        if PromotionList:
            promotion_discount = next((promo["PromotionAmount"]["CurrencyAmount"] for promo in PromotionList if promo["PromotionAmount"]["CurrencyAmount"] != 0), 0)
        logger.info(amazon_order_id)
        print("principal,fba_fee,commission,shipping_charge,promotion_discount, COG",principal,fba_fee,commission,shipping_charge,promotion_discount,COG)
        final_profit = principal - float(COG) - abs(fba_fee) - abs(commission) + abs(shipping_charge) - abs(promotion_discount)
        logger.info("final profit == %s", final_profit)
        for po, used_quantity in used_pos:
            po.profit += Decimal(final_profit) * Decimal(used_quantity) / Decimal(quantity)
            po.available_quantity -= used_quantity
            total_cog = po.amount_per_unit * used_quantity  # Total cost of goods in this PO
            if total_cog > 0:
                po.profit_percentage = (po.profit / total_cog) * 100
            po.save()
        ord = Order.objects.get(AmazonOrderId=amazon_order_id)
        ord.profit = final_profit
        ord.profit_percentage = (Decimal(final_profit) / COG) * 100 if COG > 0 else 0
        ord.have_profit = True
        ord.save()


#Driver Code
def main():
    update_profit()