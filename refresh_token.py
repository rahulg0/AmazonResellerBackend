import requests
import time
import json
from datetime import datetime, timedelta, timezone

BASE_URL = 'https://sellingpartnerapi-na.amazon.com'
REFRESH_URL = 'https://api.amazon.com/auth/o2/token'

CLIENT_ID = ""
CLIENT_SECRET = ""
REFRESH_TOKEN = ""
marketplace_id = ""


def get_amazon_oauth_token(refresh_token, client_id, client_secret):
    url = REFRESH_URL
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    data = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret
    }
    response = requests.post(url, headers=headers, data=data)
    return response.json().get("access_token")


def get_amazon_orders(access_token):
    url = BASE_URL + "/orders/v0/orders"
    created_after = (datetime.now(timezone.utc) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {
        "CreatedAfter": '2025-03-01T00:00:00Z',
        "OrderStatus": "Delivered",
        "MarketplaceIds": marketplace_id
    }
    headers = {
        "accept": "application/json",
        "x-amz-access-token": access_token
    }
    response = requests.get(url, headers=headers, params=params)
    return response.json()

access_token = get_amazon_oauth_token(REFRESH_TOKEN, CLIENT_ID, CLIENT_SECRET)
print(get_amazon_orders(access_token))
