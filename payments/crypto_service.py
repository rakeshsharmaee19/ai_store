"""
Non-custodial crypto payment verification.

IMPORTANT SECURITY NOTE:
This project NEVER stores or uses private keys. It only VERIFIES that a
transaction hash submitted by the client actually exists on-chain, was sent
to our configured receiving address, on the configured chain, for at least
the expected amount, succeeded, and has enough confirmations. The backend
never trusts a transaction hash at face value.

Provider abstraction: a project could support multiple chains by adding
another class that implements CryptoProvider's interface.
"""
import abc
import logging
from decimal import Decimal
from typing import NamedTuple

from django.conf import settings

logger = logging.getLogger("payments")


class VerifiedTransaction(NamedTuple):
    tx_hash: str
    success: bool
    to_address: str
    value_wei: int
    confirmations: int
    chain_id: int


class CryptoProvider(abc.ABC):
    @abc.abstractmethod
    def get_transaction(self, tx_hash: str) -> VerifiedTransaction | None:
        ...


class Web3Provider(CryptoProvider):
    """Real provider backed by web3.py against a configured RPC endpoint."""

    def __init__(self, rpc_url: str, chain_id: int):
        self.rpc_url = rpc_url
        self.chain_id = chain_id

    def _client(self):
        from web3 import Web3

        return Web3(Web3.HTTPProvider(self.rpc_url))

    def get_transaction(self, tx_hash: str) -> VerifiedTransaction | None:
        w3 = self._client()
        try:
            tx = w3.eth.get_transaction(tx_hash)
            receipt = w3.eth.get_transaction_receipt(tx_hash)
        except Exception:  # noqa: BLE001 - any RPC error means "not verifiable"
            logger.warning("crypto_tx_lookup_failed tx_hash=%s", tx_hash)
            return None

        if tx is None or receipt is None:
            return None

        latest_block = w3.eth.block_number
        confirmations = max(0, latest_block - receipt["blockNumber"])

        return VerifiedTransaction(
            tx_hash=tx_hash,
            success=receipt["status"] == 1,
            to_address=(tx["to"] or "").lower(),
            value_wei=tx["value"],
            confirmations=confirmations,
            chain_id=w3.eth.chain_id,
        )


class TestnetProvider(CryptoProvider):
    """
    Deterministic fake provider used in local dev/tests so the flow can be
    exercised without a real RPC endpoint or real funds.
    """

    def __init__(self):
        self._fixtures: dict[str, VerifiedTransaction] = {}

    def register_fixture(self, tx: VerifiedTransaction) -> None:
        self._fixtures[tx.tx_hash] = tx

    def get_transaction(self, tx_hash: str) -> VerifiedTransaction | None:
        return self._fixtures.get(tx_hash)


class CryptoPaymentService:
    """
    Verifies a claimed crypto payment against the configured provider.
    Never marks a payment complete based solely on client-supplied data.
    """

    def __init__(self, provider: CryptoProvider | None = None):
        self.provider = provider or Web3Provider(
            rpc_url=settings.CRYPTO_RPC_URL, chain_id=settings.CRYPTO_CHAIN_ID
        )
        self.receiving_address = settings.CRYPTO_RECEIVING_ADDRESS.lower()
        self.chain_id = settings.CRYPTO_CHAIN_ID
        self.min_confirmations = settings.CRYPTO_MIN_CONFIRMATIONS

    def verify_transaction(self, *, tx_hash: str, expected_amount_wei: int) -> VerifiedTransaction:
        from common.exceptions import InvalidCryptoTransaction

        tx = self.provider.get_transaction(tx_hash)
        if tx is None:
            raise InvalidCryptoTransaction("Transaction not found on-chain.")
        if tx.chain_id != self.chain_id:
            raise InvalidCryptoTransaction("Transaction is on the wrong chain.")
        if tx.to_address != self.receiving_address:
            raise InvalidCryptoTransaction("Transaction recipient does not match the configured receiving address.")
        if not tx.success:
            raise InvalidCryptoTransaction("Transaction reverted / failed on-chain.")
        if tx.value_wei < expected_amount_wei:
            raise InvalidCryptoTransaction("Transaction amount is less than the expected payment amount.")
        if tx.confirmations < self.min_confirmations:
            raise InvalidCryptoTransaction(
                f"Transaction only has {tx.confirmations} confirmations; {self.min_confirmations} required."
            )
        return tx

    @staticmethod
    def amount_to_wei(amount: Decimal, wei_per_unit: int = 10**18) -> int:
        """Simplified conversion helper for the demo (treats `amount` as a whole-coin amount)."""
        return int(amount * wei_per_unit)
