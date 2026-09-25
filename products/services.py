"""Product-related business logic."""
from django.db import transaction

from common.exceptions import InsufficientStock
from .models import Product


def get_active_product_or_none(product_id: int) -> Product | None:
    return Product.objects.filter(id=product_id, is_active=True).first()


@transaction.atomic
def reserve_stock(*, product_id: int, quantity: int) -> Product:
    """
    Atomically decrement stock for a product, preventing race conditions using
    a SELECT ... FOR UPDATE row lock plus a conditional update.
    """
    product = Product.objects.select_for_update().get(id=product_id)
    if not product.is_active:
        raise InsufficientStock("Product is not currently available.")
    if product.stock_quantity < quantity:
        raise InsufficientStock(f"Only {product.stock_quantity} units of '{product.name}' are in stock.")
    product.stock_quantity -= quantity
    product.save(update_fields=["stock_quantity", "updated_at"])
    return product


@transaction.atomic
def release_stock(*, product_id: int, quantity: int) -> Product:
    """Return stock to inventory, e.g. after an order cancellation."""
    product = Product.objects.select_for_update().get(id=product_id)
    product.stock_quantity += quantity
    product.save(update_fields=["stock_quantity", "updated_at"])
    return product
