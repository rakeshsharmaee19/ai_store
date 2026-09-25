from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Product

User = get_user_model()


class ProductTests(APITestCase):
    def setUp(self):
        self.product = Product.objects.create(name="Widget", price=Decimal("9.99"), stock_quantity=10)
        self.staff = User.objects.create_user(email="staff@example.com", password="StrongPassword123!", is_staff=True)
        self.customer = User.objects.create_user(email="cust@example.com", password="StrongPassword123!")

    def auth(self, user):
        self.client.force_authenticate(user=user)

    def test_list_products_public(self):
        response = self.client.get(reverse("product-list"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)

    def test_retrieve_product_public(self):
        response = self.client.get(reverse("product-detail", args=[self.product.id]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["name"], "Widget")

    def test_staff_can_create_product(self):
        self.auth(self.staff)
        payload = {"name": "New Product", "price": "19.99", "stock_quantity": 5}
        response = self.client.post(reverse("product-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

    def test_normal_user_cannot_create_product(self):
        self.auth(self.customer)
        payload = {"name": "New Product", "price": "19.99", "stock_quantity": 5}
        response = self.client.post(reverse("product-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_anonymous_cannot_create_product(self):
        payload = {"name": "New Product", "price": "19.99", "stock_quantity": 5}
        response = self.client.post(reverse("product-list"), payload, format="json")
        # Unauthenticated requests are rejected by JWT authentication itself (401)
        # before permission checks (403) are even evaluated.
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
