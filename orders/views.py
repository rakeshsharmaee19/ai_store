from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from .models import Order
from .permissions import IsOrderOwnerOrStaff
from .serializers import CreateOrderSerializer, OrderSerializer
from .services import cancel_order, create_order


class OrderViewSet(mixins.CreateModelMixin, mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """
    POST /api/orders/            - create an order (server computes totals)
    GET  /api/orders/             - list current user's orders (staff sees all)
    GET  /api/orders/{id}/        - retrieve a single order
    POST /api/orders/{id}/cancel/ - cancel a pending order
    """

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsOrderOwnerOrStaff]

    def get_queryset(self):
        qs = Order.objects.prefetch_related("items", "items__product")
        if self.request.user.is_staff:
            return qs
        return qs.filter(user=self.request.user)

    def create(self, request, *args, **kwargs):
        input_serializer = CreateOrderSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        order = create_order(user=request.user, items=input_serializer.validated_data["items"])
        return Response(OrderSerializer(order).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        order = self.get_object()
        order = cancel_order(order=order)
        return Response(OrderSerializer(order).data)
