from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from common.exceptions import InvalidCryptoTransaction
from orders.models import Order
from payments.crypto_service import CryptoPaymentService, TestnetProvider, VerifiedTransaction
from payments.models import PaymentTransaction
from products.models import Product

User = get_user_model()

RECEIVING_ADDRESS = "0x000000000000000000000000000000000000aa"


@override_settings(CRYPTO_RECEIVING_ADDRESS=RECEIVING_ADDRESS, CRYPTO_CHAIN_ID=1, CRYPTO_MIN_CONFIRMATIONS=3)
class CryptoVerificationTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="crypto@example.com", password="StrongPassword123!")
        self.product = Product.objects.create(name="CryptoItem", price=Decimal("1.00"), stock_quantity=5)
        self.order = Order.objects.create(user=self.user, order_number="ORD-CRYPTO1", total_amount=Decimal("1.00"))
        self.payment = PaymentTransaction.objects.create(
            order=self.order, user=self.user, payment_method="CRYPTO", amount=Decimal("1.00"),
            idempotency_key="crypto-key-1",
        )
        self.expected_wei = CryptoPaymentService.amount_to_wei(self.payment.amount)
        self.provider = TestnetProvider()
        self.service = CryptoPaymentService(provider=self.provider)

    def test_valid_transaction_verifies(self):
        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xvalid", success=True, to_address=RECEIVING_ADDRESS,
            value_wei=self.expected_wei, confirmations=5, chain_id=1,
        ))
        tx = self.service.verify_transaction(tx_hash="0xvalid", expected_amount_wei=self.expected_wei)
        self.assertTrue(tx.success)

    def test_wrong_recipient_rejected(self):
        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xwrongrecipient", success=True, to_address="0xdeadbeef",
            value_wei=self.expected_wei, confirmations=5, chain_id=1,
        ))
        with self.assertRaises(InvalidCryptoTransaction):
            self.service.verify_transaction(tx_hash="0xwrongrecipient", expected_amount_wei=self.expected_wei)

    def test_wrong_chain_rejected(self):
        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xwrongchain", success=True, to_address=RECEIVING_ADDRESS,
            value_wei=self.expected_wei, confirmations=5, chain_id=999,
        ))
        with self.assertRaises(InvalidCryptoTransaction):
            self.service.verify_transaction(tx_hash="0xwrongchain", expected_amount_wei=self.expected_wei)

    def test_insufficient_amount_rejected(self):
        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xlowamount", success=True, to_address=RECEIVING_ADDRESS,
            value_wei=self.expected_wei - 1, confirmations=5, chain_id=1,
        ))
        with self.assertRaises(InvalidCryptoTransaction):
            self.service.verify_transaction(tx_hash="0xlowamount", expected_amount_wei=self.expected_wei)

    def test_failed_transaction_rejected(self):
        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xfailed", success=False, to_address=RECEIVING_ADDRESS,
            value_wei=self.expected_wei, confirmations=5, chain_id=1,
        ))
        with self.assertRaises(InvalidCryptoTransaction):
            self.service.verify_transaction(tx_hash="0xfailed", expected_amount_wei=self.expected_wei)

    def test_insufficient_confirmations_rejected(self):
        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xlowconf", success=True, to_address=RECEIVING_ADDRESS,
            value_wei=self.expected_wei, confirmations=1, chain_id=1,
        ))
        with self.assertRaises(InvalidCryptoTransaction):
            self.service.verify_transaction(tx_hash="0xlowconf", expected_amount_wei=self.expected_wei)

    def test_duplicate_verification_is_idempotent(self):
        from payments.services import complete_payment

        self.provider.register_fixture(VerifiedTransaction(
            tx_hash="0xdup", success=True, to_address=RECEIVING_ADDRESS,
            value_wei=self.expected_wei, confirmations=5, chain_id=1,
        ))
        tx = self.service.verify_transaction(tx_hash="0xdup", expected_amount_wei=self.expected_wei)
        complete_payment(payment=self.payment, provider_transaction_id=tx.tx_hash)
        # Second call should be a safe no-op, not raise or double-mark the order.
        result = complete_payment(payment=self.payment, provider_transaction_id=tx.tx_hash)
        self.assertEqual(result.status, "COMPLETED")
