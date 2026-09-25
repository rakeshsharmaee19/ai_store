"""
Crypto/wallet read tools. `verify_crypto_transaction` performs REAL backend
verification via CryptoPaymentService -- it never simply trusts whatever
the LLM (or, transitively, the end user) claims about a transaction hash.
"""
from common.exceptions import ToolExecutionError
from payments.crypto_service import CryptoPaymentService
from payments.models import PaymentTransaction

from .registry import ToolDefinition, registry


def get_crypto_payment_status(*, payment_id: int) -> dict:
    payment = PaymentTransaction.objects.filter(id=payment_id, payment_method="CRYPTO").first()
    if payment is None:
        raise ToolExecutionError(f"No crypto payment found with id={payment_id}.")
    return {
        "id": payment.id,
        "status": payment.status,
        "amount": str(payment.amount),
        "provider_transaction_id": payment.provider_transaction_id,
        "failure_reason": payment.failure_reason,
    }


def verify_crypto_transaction(*, payment_id: int, tx_hash: str) -> dict:
    """
    Runs the SAME on-chain verification used by the real payment API
    endpoint. This never marks a payment complete based on agent/LLM say-so
    alone -- CryptoPaymentService independently checks the chain.
    """
    from payments.services import complete_payment

    payment = PaymentTransaction.objects.filter(id=payment_id, payment_method="CRYPTO").first()
    if payment is None:
        raise ToolExecutionError(f"No crypto payment found with id={payment_id}.")

    if payment.status == "COMPLETED":
        return {"id": payment.id, "status": "COMPLETED", "note": "Already verified (idempotent)."}

    expected_wei = CryptoPaymentService.amount_to_wei(payment.amount)
    try:
        tx = CryptoPaymentService().verify_transaction(tx_hash=tx_hash, expected_amount_wei=expected_wei)
    except Exception as exc:  # noqa: BLE001 - surface as a tool-level failure, not a crash
        raise ToolExecutionError(str(exc)) from exc

    payment = complete_payment(payment=payment, provider_transaction_id=tx.tx_hash)
    return {"id": payment.id, "status": payment.status, "tx_hash": tx.tx_hash, "confirmations": tx.confirmations}


registry.register(
    ToolDefinition(
        name="get_crypto_payment_status",
        description="Get the current status of a crypto payment by its payment id.",
        parameters={
            "type": "object",
            "properties": {"payment_id": {"type": "integer"}},
            "required": ["payment_id"],
        },
        handler=get_crypto_payment_status,
        required_permission="agent.can_read_crypto",
        read_only=True,
        requires_confirmation=False,
    )
)

registry.register(
    ToolDefinition(
        name="verify_crypto_transaction",
        description=(
            "Independently verify a claimed crypto transaction hash against the blockchain via Web3 RPC, "
            "and mark the payment completed only if verification succeeds. Does NOT trust the tx_hash at face value."
        ),
        parameters={
            "type": "object",
            "properties": {
                "payment_id": {"type": "integer"},
                "tx_hash": {"type": "string"},
            },
            "required": ["payment_id", "tx_hash"],
        },
        handler=verify_crypto_transaction,
        required_permission="agent.can_read_crypto",
        read_only=False,
        requires_confirmation=False,
    )
)
