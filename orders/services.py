"""Order business logic: pricing, stock reservation, transitions.

All of this happens server-side. The client only supplies product ids and
quantities -- amounts are ALWAYS computed here from the authoritative
Product.price, never trusted from the request body.
"""
from django.db import transaction

from common.constants import (
    ORDER_CANCELLABLE_STATUSES,
    ORDER_CANCELLED,
    ORDER_PENDING_PAYMENT,
)
from common.exceptions import InvalidOrderState
from common.utils import generate_order_number
from products.models import Product
from products.services import release_stock, reserve_stock

from .models import Order, OrderItem


@transaction.atomic
def create_order(*, user, items: list[dict]) -> Order:
    """
    items: [{"product_id": int, "quantity": int}, ...]

    1. Validate each product exists and is active.
    2. Reserve stock atomically (row-locked) to prevent race conditions.
    3. Snapshot unit_price at purchase time.
    4. Compute total server-side.
    """
    order = Order.objects.create(
        user=user,
        order_number=generate_order_number(),
        status=ORDER_PENDING_PAYMENT,
        total_amount=0,
    )

    total = 0
    order_items = []
    for entry in items:
        product = Product.objects.select_for_update().get(id=entry["product_id"])
        quantity = entry["quantity"]

        reserve_stock(product_id=product.id, quantity=quantity)

        unit_price = product.price
        subtotal = unit_price * quantity
        total += subtotal

        order_items.append(
            OrderItem(order=order, product=product, quantity=quantity, unit_price=unit_price, subtotal=subtotal)
        )

    OrderItem.objects.bulk_create(order_items)

    order.total_amount = total
    order.save(update_fields=["total_amount", "updated_at"])
    return order


@transaction.atomic
def cancel_order(*, order: Order) -> Order:
    order = Order.objects.select_for_update().get(id=order.id)
    if order.status not in ORDER_CANCELLABLE_STATUSES:
        raise InvalidOrderState(f"Order in status '{order.status}' cannot be cancelled.")

    for item in order.items.select_related("product"):
        release_stock(product_id=item.product_id, quantity=item.quantity)

    order.status = ORDER_CANCELLED
    order.save(update_fields=["status", "updated_at"])
    return order


def mark_order_paid(*, order: Order) -> Order:
    from common.constants import ORDER_PAID

    order.status = ORDER_PAID
    order.save(update_fields=["status", "updated_at"])
    return order


def mark_order_failed(*, order: Order) -> Order:
    from common.constants import ORDER_FAILED

    order.status = ORDER_FAILED
    order.save(update_fields=["status", "updated_at"])
    return order
