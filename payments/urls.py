from django.urls import path

from .views import (
    CreateCryptoPaymentView,
    CreateStripePaymentView,
    PaymentHistoryView,
    RefundPaymentView,
    VerifyCryptoPaymentView,
)
from .webhooks import StripeWebhookView

urlpatterns = [
    path("", PaymentHistoryView.as_view(), name="payment-history"),
    path("stripe/create/", CreateStripePaymentView.as_view(), name="stripe-create"),
    path("stripe/webhook/", StripeWebhookView.as_view(), name="stripe-webhook"),
    path("crypto/create/", CreateCryptoPaymentView.as_view(), name="crypto-create"),
    path("crypto/verify/", VerifyCryptoPaymentView.as_view(), name="crypto-verify"),
    path("<int:pk>/refund/", RefundPaymentView.as_view(), name="payment-refund"),
]
