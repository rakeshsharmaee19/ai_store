"""Celery tasks for the agent app."""
import logging

from celery import shared_task

logger = logging.getLogger("agent")


@shared_task
def send_customer_email_task(*, user_id: int, subject: str, body: str) -> dict:
    """
    Placeholder for real email delivery (SES/SendGrid/etc). Kept as a
    background task so the agent's HTTP request never blocks on outbound
    email delivery.
    """
    logger.info("send_customer_email user_id=%s subject=%s", user_id, subject)
    # Real implementation would call an email provider here.
    return {"user_id": user_id, "subject": subject, "sent": True}


@shared_task
def analyze_large_transaction_task(payment_id: int) -> dict:
    """
    Example of a heavier background job: flags large transactions for
    review. Demonstrates Celery + DB access outside the request cycle.
    """
    from payments.models import PaymentTransaction

    payment = PaymentTransaction.objects.filter(id=payment_id).first()
    if payment is None:
        return {"status": "not_found"}

    is_large = payment.amount >= 1000
    logger.info("large_transaction_analysis payment_id=%s large=%s", payment_id, is_large)
    return {"payment_id": payment_id, "flagged_for_review": is_large}
