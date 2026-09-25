"""Read-only tools exposing order data to the agent."""
from common.exceptions import ToolExecutionError
from orders.models import Order

from .registry import ToolDefinition, registry


def _serialize_order(order: Order) -> dict:
    return {
        "id": order.id,
        "order_number": order.order_number,
        "user_id": order.user_id,
        "status": order.status,
        "total_amount": str(order.total_amount),
        "currency": order.currency,
        "items": [
            {
                "product_id": item.product_id,
                "product_name": item.product.name,
                "quantity": item.quantity,
                "unit_price": str(item.unit_price),
                "subtotal": str(item.subtotal),
            }
            for item in order.items.select_related("product").all()
        ],
        "created_at": order.created_at.isoformat(),
        "updated_at": order.updated_at.isoformat(),
    }


def get_order(*, order_number: str) -> dict:
    order = Order.objects.filter(order_number=order_number).first()
    if order is None:
        raise ToolExecutionError(f"No order found with order_number='{order_number}'.")
    return _serialize_order(order)


def get_user_orders(*, user_id: int, limit: int = 5) -> dict:
    orders = Order.objects.filter(user_id=user_id).order_by("-created_at")[: min(limit, 50)]
    return {"orders": [_serialize_order(o) for o in orders]}


registry.register(
    ToolDefinition(
        name="get_order",
        description="Get full details of an order, including its items, by its human-readable order_number (e.g. 'ORD-1001').",
        parameters={
            "type": "object",
            "properties": {"order_number": {"type": "string"}},
            "required": ["order_number"],
        },
        handler=get_order,
        required_permission="agent.can_read_order",
        read_only=True,
        requires_confirmation=False,
    )
)

registry.register(
    ToolDefinition(
        name="get_user_orders",
        description="List the most recent orders belonging to a given user id.",
        parameters={
            "type": "object",
            "properties": {
                "user_id": {"type": "integer"},
                "limit": {"type": "integer", "default": 5, "description": "Max number of orders to return (max 50)."},
            },
            "required": ["user_id"],
        },
        handler=get_user_orders,
        required_permission="agent.can_read_order",
        read_only=True,
        requires_confirmation=False,
    )
)
