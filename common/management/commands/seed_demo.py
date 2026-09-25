"""
Management command: python manage.py seed_demo

Creates demo users, products, orders and example payment transactions
(including a successful Stripe payment, a failed Stripe payment, a
completed crypto payment, and a failed crypto verification) so the API and
agent can be explored immediately after `docker compose up`.

ALL CREDENTIALS BELOW ARE DEMO-ONLY. Never reuse them in production.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.management.base import BaseCommand
from django.db import transaction

from orders.models import Order, OrderItem
from payments.models import PaymentTransaction
from products.models import Product

User = get_user_model()


class Command(BaseCommand):
    help = "Seed the database with demo users, products, orders and transactions."

    @transaction.atomic
    def handle(self, *args, **options):
        self.stdout.write("Seeding demo data...")

        admin, _ = User.objects.get_or_create(
            email="admin@example.com",
            defaults={"first_name": "Admin", "last_name": "User", "is_staff": True, "is_superuser": True},
        )
        admin.set_password("Admin12345!")
        admin.is_staff = True
        admin.is_superuser = True
        admin.save()

        support, _ = User.objects.get_or_create(
            email="support@example.com",
            defaults={"first_name": "Support", "last_name": "Agent", "is_staff": True},
        )
        support.set_password("Support12345!")
        support.is_staff = True
        support.save()
        self._grant_permissions(support, [
            "can_read_user", "can_read_product", "can_read_order", "can_read_payment", "can_read_crypto",
        ])

        senior_support, _ = User.objects.get_or_create(
            email="senior_support@example.com",
            defaults={"first_name": "Senior", "last_name": "Support", "is_staff": True},
        )
        senior_support.set_password("SeniorSupport12345!")
        senior_support.is_staff = True
        senior_support.save()
        self._grant_permissions(senior_support, [
            "can_read_user", "can_read_product", "can_read_order", "can_read_payment", "can_read_crypto",
            "can_cancel_order", "can_email_customer",
        ])

        finance_admin, _ = User.objects.get_or_create(
            email="finance_admin@example.com",
            defaults={"first_name": "Finance", "last_name": "Admin", "is_staff": True},
        )
        finance_admin.set_password("FinanceAdmin12345!")
        finance_admin.is_staff = True
        finance_admin.save()
        self._grant_permissions(finance_admin, [
            "can_read_user", "can_read_product", "can_read_order", "can_read_payment", "can_read_crypto",
            "can_refund_payment",
        ])

        customer, _ = User.objects.get_or_create(
            email="customer@example.com",
            defaults={"first_name": "Demo", "last_name": "Customer"},
        )
        customer.set_password("Customer12345!")
        customer.save()

        widget, _ = Product.objects.get_or_create(
            name="Demo Widget", defaults={"price": Decimal("19.99"), "stock_quantity": 100, "description": "A simple demo widget."}
        )
        gadget, _ = Product.objects.get_or_create(
            name="Demo Gadget", defaults={"price": Decimal("49.50"), "stock_quantity": 50, "description": "A fancier demo gadget."}
        )
        Product.objects.get_or_create(
            name="Demo Gizmo", defaults={"price": Decimal("99.00"), "stock_quantity": 20, "description": "A premium demo gizmo."}
        )

        # Successful Stripe order
        order_paid, created = Order.objects.get_or_create(
            order_number="ORD-DEMO001",
            defaults={"user": customer, "status": "PAID", "total_amount": Decimal("19.99")},
        )
        if created:
            OrderItem.objects.create(order=order_paid, product=widget, quantity=1, unit_price=widget.price, subtotal=widget.price)
            PaymentTransaction.objects.create(
                order=order_paid, user=customer, payment_method="STRIPE", amount=Decimal("19.99"),
                status="COMPLETED", provider="stripe", provider_transaction_id="pi_demo_success",
                idempotency_key="seed-key-1",
            )

        # Failed Stripe order
        order_failed, created = Order.objects.get_or_create(
            order_number="ORD-DEMO002",
            defaults={"user": customer, "status": "FAILED", "total_amount": Decimal("49.50")},
        )
        if created:
            OrderItem.objects.create(order=order_failed, product=gadget, quantity=1, unit_price=gadget.price, subtotal=gadget.price)
            PaymentTransaction.objects.create(
                order=order_failed, user=customer, payment_method="STRIPE", amount=Decimal("49.50"),
                status="FAILED", provider="stripe", provider_transaction_id="pi_demo_failed",
                idempotency_key="seed-key-2", failure_reason="Your card was declined.",
            )

        # Completed crypto order
        order_crypto, created = Order.objects.get_or_create(
            order_number="ORD-DEMO003",
            defaults={"user": customer, "status": "PAID", "total_amount": Decimal("19.99")},
        )
        if created:
            OrderItem.objects.create(order=order_crypto, product=widget, quantity=1, unit_price=widget.price, subtotal=widget.price)
            PaymentTransaction.objects.create(
                order=order_crypto, user=customer, payment_method="CRYPTO", amount=Decimal("19.99"),
                status="COMPLETED", provider="web3", provider_transaction_id="0xdemo_success_hash",
                idempotency_key="seed-key-3",
            )

        # Failed crypto verification order
        order_crypto_failed, created = Order.objects.get_or_create(
            order_number="ORD-DEMO004",
            defaults={"user": customer, "status": "PENDING_PAYMENT", "total_amount": Decimal("49.50")},
        )
        if created:
            OrderItem.objects.create(order=order_crypto_failed, product=gadget, quantity=1, unit_price=gadget.price, subtotal=gadget.price)
            PaymentTransaction.objects.create(
                order=order_crypto_failed, user=customer, payment_method="CRYPTO", amount=Decimal("49.50"),
                status="FAILED", provider="web3", idempotency_key="seed-key-4",
                failure_reason="Transaction sent to wrong recipient address.",
            )

        self.stdout.write(self.style.SUCCESS("Demo data seeded successfully."))
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("DEMO CREDENTIALS (do not use in production):"))
        self.stdout.write("  admin@example.com            / Admin12345!            (superuser)")
        self.stdout.write("  support@example.com           / Support12345!         (read-only agent tools)")
        self.stdout.write("  senior_support@example.com     / SeniorSupport12345!   (+ cancel_order, send_customer_email)")
        self.stdout.write("  finance_admin@example.com      / FinanceAdmin12345!    (+ refund_payment)")
        self.stdout.write("  customer@example.com           / Customer12345!        (regular customer)")

    def _grant_permissions(self, user, codenames: list[str]) -> None:
        perms = Permission.objects.filter(codename__in=codenames, content_type__app_label="agent")
        user.user_permissions.add(*perms)
