"""Read-only tools exposing product catalog data to the agent."""
from products.models import Product

from .registry import ToolDefinition, registry


def list_products(*, only_active: bool = True, limit: int = 20) -> dict:
    qs = Product.objects.all()
    if only_active:
        qs = qs.filter(is_active=True)
    qs = qs.order_by("-created_at")[: min(limit, 100)]
    return {
        "products": [
            {
                "id": p.id,
                "name": p.name,
                "price": str(p.price),
                "currency": p.currency,
                "stock_quantity": p.stock_quantity,
                "is_active": p.is_active,
            }
            for p in qs
        ]
    }


def get_product(*, product_id: int) -> dict:
    from common.exceptions import ToolExecutionError

    product = Product.objects.filter(id=product_id).first()
    if product is None:
        raise ToolExecutionError(f"No product found with id={product_id}.")
    return {
        "id": product.id,
        "name": product.name,
        "description": product.description,
        "price": str(product.price),
        "currency": product.currency,
        "stock_quantity": product.stock_quantity,
        "is_active": product.is_active,
    }


registry.register(
    ToolDefinition(
        name="list_products",
        description="List products in the catalog, optionally filtering to only active products.",
        parameters={
            "type": "object",
            "properties": {
                "only_active": {"type": "boolean", "description": "If true, only return active products.", "default": True},
                "limit": {"type": "integer", "description": "Maximum number of products to return (max 100).", "default": 20},
            },
            "required": [],
        },
        handler=list_products,
        required_permission="agent.can_read_product",
        read_only=True,
        requires_confirmation=False,
    )
)

registry.register(
    ToolDefinition(
        name="get_product",
        description="Get details of a single product by its numeric id.",
        parameters={
            "type": "object",
            "properties": {"product_id": {"type": "integer"}},
            "required": ["product_id"],
        },
        handler=get_product,
        required_permission="agent.can_read_product",
        read_only=True,
        requires_confirmation=False,
    )
)
