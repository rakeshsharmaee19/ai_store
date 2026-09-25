from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

User = get_user_model()


class RegistrationTests(APITestCase):
    def test_register_success(self):
        url = reverse("auth-register")
        payload = {
            "email": "newuser@example.com",
            "password": "StrongPassword123!",
            "first_name": "New",
            "last_name": "User",
        }
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())
        self.assertNotIn("password", response.data)

    def test_register_duplicate_email(self):
        User.objects.create_user(email="dup@example.com", password="StrongPassword123!")
        url = reverse("auth-register")
        payload = {"email": "dup@example.com", "password": "StrongPassword123!"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_weak_password(self):
        url = reverse("auth-register")
        payload = {"email": "weak@example.com", "password": "weak"}
        response = self.client.post(url, payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class LoginTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="login@example.com", password="StrongPassword123!")

    def test_login_success_returns_tokens(self):
        url = reverse("auth-login")
        response = self.client.post(url, {"email": "login@example.com", "password": "StrongPassword123!"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_login_wrong_password(self):
        url = reverse("auth-login")
        response = self.client.post(url, {"email": "login@example.com", "password": "WrongPassword!"}, format="json")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_requires_authentication(self):
        url = reverse("auth-me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_me_returns_profile_when_authenticated(self):
        login_url = reverse("auth-login")
        tokens = self.client.post(login_url, {"email": "login@example.com", "password": "StrongPassword123!"}, format="json").data
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        response = self.client.get(reverse("auth-me"))
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "login@example.com")
