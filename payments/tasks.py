"""Celery tasks for payments (kept out of the request/response cycle)."""
import logging

from celery import shared_task

logger = logging.getLogger("payments")


@shared_task(bind=True, max_retries=3)
def verify_crypto_transaction_task(self, payment_id: int, tx_hash: str):
    """
    Background verification of a crypto transaction. Useful when a client
    wants to fire-and-forget verification rather than block on an RPC call.
    """
    from .crypto_service import CryptoPaymentService
    from .models import PaymentTransaction
    from .services import complete_payment

    try:
        payment = PaymentTransaction.objects.select_related("order").get(id=payment_id)
        if payment.status == "COMPLETED":
            return {"status": "already_completed"}

        expected_wei = CryptoPaymentService.amount_to_wei(payment.amount)
        tx = CryptoPaymentService().verify_transaction(tx_hash=tx_hash, expected_amount_wei=expected_wei)
        complete_payment(payment=payment, provider_transaction_id=tx.tx_hash)
        return {"status": "completed"}
    except Exception as exc:  # noqa: BLE001
        logger.warning("crypto_verification_task_failed payment_id=%s error=%s", payment_id, exc)
        raise self.retry(exc=exc, countdown=30)
