from rest_framework import serializers

from common.validators import validate_positive_quantity
from products.models import Product

from .models import Order, OrderItem


class OrderItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = OrderItem
        fields = ["id", "product", "product_name", "quantity", "unit_price", "subtotal"]
        read_only_fields = ["id", "unit_price", "subtotal", "product_name"]


class OrderSerializer(serializers.ModelSerializer):
    items = OrderItemSerializer(many=True, read_only=True)

    class Meta:
        model = Order
        fields = ["id", "order_number", "status", "total_amount", "currency", "items", "created_at", "updated_at"]
        read_only_fields = fields


class CreateOrderItemInputSerializer(serializers.Serializer):
    product_id = serializers.IntegerField()
    quantity = serializers.IntegerField(validators=[validate_positive_quantity])

    def validate_product_id(self, value):
        if not Product.objects.filter(id=value).exists():
            raise serializers.ValidationError("Product does not exist.")
        return value


class CreateOrderSerializer(serializers.Serializer):
    """
    Input serializer for order creation. Note: this ONLY validates shape.
    All pricing/stock/business rules are enforced in orders.services, never
    trusting client-supplied totals.
    """

    items = CreateOrderItemInputSerializer(many=True)

    def validate_items(self, value):
        if not value:
            raise serializers.ValidationError("At least one item is required.")
        return value
