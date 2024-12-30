# Amazon Reseller Backend

This is a Django-based backend for managing Amazon reseller operations. It includes models for purchase orders and orders, along with APIs for creating, retrieving, and deleting these records.

## Prerequisites

- Python 3.x
- PostgreSQL
- Virtualenv (optional but recommended)

## Setup Instructions

### 1. Clone the Repository

```sh
git clone https://github.com/rahulg0/AmazonResellerBackend.git
cd AmazonResellerBackend
```

### 2. Create and Activate a Virtual Environment

```
python -m venv venv
source venv/bin/activate  # On Windows use `venv\Scripts\activate`
```

### 3. Install Dependencies

```
pip install -r requirements.txt
```

### 4. Configure PostgreSQL Database

Ensure you have PostgreSQL installed and running. Create a database and a user for the project:

```
CREATE DATABASE AmazonResellerBackendDB;
CREATE USER amazonreseller WITH PASSWORD 'amazon123';
GRANT ALL PRIVILEGES ON DATABASE AmazonResellerBackendDB TO amazonreseller;
```

### 5. Apply Migrations

```
python manage.py migrate
```

### 6. Run the Development Server

```
python manage.py runserver
```

## API Endpoints

* `POST /api/purchase-order`: Create a new purchase order.
* `GET /api/purchase-order`: Retrieve all purchase orders.
* `DELETE /api/purchase-order`: Delete a purchase order by `order_uuid`.
* `POST /api/orders`: Create new orders.
* `GET /api/orders`: Retrieve all orders.
* `DELETE /api/orders`: Delete an order by `AmazonOrderId`.

## Project Structure

```
api/
    __init__.py
    admin.py
    apps.py
    migrations/
        __init__.py
        ...
    models.py
    serializers.py
    tests.py
    urls.py
    views.py
backend/
    __init__.py
    asgi.py
    settings.py
    urls.py
    wsgi.py
manage.py
media/
    invoices/
readme.md
requirements.txt
```
