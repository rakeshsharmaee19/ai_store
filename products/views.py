from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, viewsets

from .models import Product
from .permissions import IsStaffOrReadOnly
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    """
    GET    /api/products/        (public)
    GET    /api/products/{id}/   (public)
    POST   /api/products/        (staff)
    PUT    /api/products/{id}/   (staff)
    PATCH  /api/products/{id}/   (staff)
    DELETE /api/products/{id}/   (staff)
    """

    serializer_class = ProductSerializer
    permission_classes = [IsStaffOrReadOnly]
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["is_active", "currency"]
    search_fields = ["name", "description"]
    ordering_fields = ["price", "created_at", "stock_quantity"]

    def get_queryset(self):
        queryset = Product.objects.all()
        if not (self.request.user.is_authenticated and self.request.user.is_staff):
            queryset = queryset.filter(is_active=True)
        return queryset
