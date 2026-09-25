from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from products.models import Product

User = get_user_model()


class OrderTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="buyer@example.com", password="StrongPassword123!")
        self.other_user = User.objects.create_user(email="other@example.com", password="StrongPassword123!")
        self.product = Product.objects.create(name="Gadget", price=Decimal("25.00"), stock_quantity=5)
        self.client.force_authenticate(user=self.user)

    def test_create_order_success(self):
        payload = {"items": [{"product_id": self.product.id, "quantity": 2}]}
        response = self.client.post(reverse("order-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["total_amount"], "50.00")
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)

    def test_create_order_incorrect_product(self):
        payload = {"items": [{"product_id": 999999, "quantity": 1}]}
        response = self.client.post(reverse("order-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_create_order_insufficient_stock(self):
        payload = {"items": [{"product_id": self.product.id, "quantity": 999}]}
        response = self.client.post(reverse("order-list"), payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(response.data["error"]["code"], "INSUFFICIENT_STOCK")

    def test_ownership_prevents_viewing_others_orders(self):
        payload = {"items": [{"product_id": self.product.id, "quantity": 1}]}
        order = self.client.post(reverse("order-list"), payload, format="json").data

        self.client.force_authenticate(user=self.other_user)
        response = self.client.get(reverse("order-detail", args=[order["id"]]))
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_cancel_order(self):
        payload = {"items": [{"product_id": self.product.id, "quantity": 1}]}
        order = self.client.post(reverse("order-list"), payload, format="json").data

        response = self.client.post(reverse("order-cancel", args=[order["id"]]))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["status"], "CANCELLED")

        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 5)  # stock released
