from rest_framework import serializers
from .models import PurchaseOrder, Order
import base64

class PurchaseOrderSerializer(serializers.ModelSerializer):
    available_quantity = serializers.IntegerField(required=False)
    class Meta:
        model = PurchaseOrder
        fields = '__all__'

    def create(self, validated_data):
        if 'quantity' in validated_data and 'available_quantity' not in validated_data:
            validated_data['available_quantity'] = validated_data['quantity']
        return super().create(validated_data)

class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model = Order
        fields = '__all__'