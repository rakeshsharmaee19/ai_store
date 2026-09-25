from django.conf import settings
from django.db import models

from common.constants import ORDER_PENDING_PAYMENT, ORDER_STATUS_CHOICES


class Order(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="orders")
    order_number = models.CharField(max_length=32, unique=True, db_index=True)
    status = models.CharField(max_length=32, choices=ORDER_STATUS_CHOICES, default=ORDER_PENDING_PAYMENT)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["status"]), models.Index(fields=["user", "status"])]

    def __str__(self) -> str:
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("products.Product", on_delete=models.PROTECT, related_name="order_items")
    quantity = models.PositiveIntegerField()

    # Price is captured AT PURCHASE TIME. Never derive historical totals from
    # the live Product.price, which may change after the order is placed.
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        constraints = [
            models.CheckConstraint(check=models.Q(quantity__gt=0), name="orderitem_quantity_positive"),
        ]

    def __str__(self) -> str:
        return f"{self.product.name} x{self.quantity}"
