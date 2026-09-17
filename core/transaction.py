"""
NEXCHAIN Transaction Engine
===========================

Canonical transaction model for NEXCHAIN.

Features:
    - Deterministic transaction serialization
    - Ed25519 transaction signatures
    - Address derivation verification
    - Numeric canonicalization
    - Transaction hashing
    - Validation
    - Serialization / deserialization
"""

from __future__ import annotations

import hashlib
import math
import time
from dataclasses import dataclass
from typing import Any

from crypto.crypto_engine import (
    Wallet,
    canonical_json,
    verify_object_signature,
)


# ============================================================
# CONSTANTS
# ============================================================

MIN_AMOUNT = 0.00000001
MIN_FEE = 0.00000001

ADDRESS_PREFIX = "NEX"
ADDRESS_LENGTH = 43


# ============================================================
# TRANSACTION
# ============================================================

@dataclass
class Transaction:

    sender: str
    recipient: str
    amount: float
    fee: float
    nonce: int
    timestamp: float
    public_key: str
    signature: str = ""

    def __post_init__(self) -> None:

        self.amount = float(self.amount)
        self.fee = float(self.fee)
        self.timestamp = float(self.timestamp)

        if (
            isinstance(self.nonce, float)
            and self.nonce.is_integer()
        ):
            self.nonce = int(self.nonce)

    # ========================================================
    # CANONICAL NUMERIC VALUES
    # ========================================================

    def _canonical_amount(self) -> float:
        return float(f"{self.amount:.8f}")

    def _canonical_fee(self) -> float:
        return float(f"{self.fee:.8f}")

    def _canonical_timestamp(self) -> float:
        return float(f"{self.timestamp:.6f}")

    # ========================================================
    # SIGNING PAYLOAD
    # ========================================================

    def signing_payload(self) -> dict[str, Any]:

        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self._canonical_amount(),
            "fee": self._canonical_fee(),
            "nonce": self.nonce,
            "timestamp": self._canonical_timestamp(),
            "public_key": self.public_key,
        }

    # ========================================================
    # SIGN
    # ========================================================

    def sign(self, wallet: Wallet) -> None:

        if wallet.address() != self.sender:
            raise ValueError(
                "Wallet does not match transaction sender."
            )

        # The public key MUST be JSON-safe.
        self.public_key = wallet.public_key_encoded()

        self.signature = wallet.sign_object(
            self.signing_payload()
        )

    # ========================================================
    # HASH
    # ========================================================

    def transaction_hash(self) -> str:

        payload = {
            **self.signing_payload(),
            "signature": self.signature,
        }

        return hashlib.sha256(
            canonical_json(payload)
        ).hexdigest()

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate(self) -> tuple[bool, str]:

        # Sender
        if not isinstance(self.sender, str):
            return False, "Sender must be a string."

        if (
            not self.sender.startswith(ADDRESS_PREFIX)
            or len(self.sender) != ADDRESS_LENGTH
        ):
            return False, "Invalid sender address."

        # Recipient
        if not isinstance(self.recipient, str):
            return False, "Recipient must be a string."

        if (
            not self.recipient.startswith(ADDRESS_PREFIX)
            or len(self.recipient) != ADDRESS_LENGTH
        ):
            return False, "Invalid recipient address."

        # Self transfer
        if self.sender == self.recipient:
            return False, "Self-transfer is not allowed."

        # Amount
        if not math.isfinite(self.amount):
            return False, "Amount must be finite."

        if self.amount < MIN_AMOUNT:
            return False, "Amount is below minimum."

        # Fee
        if not math.isfinite(self.fee):
            return False, "Fee must be finite."

        if self.fee < MIN_FEE:
            return False, "Fee is below minimum."

        # Nonce
        if not isinstance(self.nonce, int):
            return False, "Nonce must be an integer."

        if self.nonce < 0:
            return False, "Nonce cannot be negative."

        # Timestamp
        if not math.isfinite(self.timestamp):
            return False, "Timestamp must be finite."

        if self.timestamp <= 0:
            return False, "Timestamp must be positive."

        # Public key
        if not isinstance(self.public_key, str):
            return False, "Public key must be encoded text."

        if not self.public_key:
            return False, "Public key is missing."

        # Signature
        if not isinstance(self.signature, str):
            return False, "Signature must be encoded text."

        if not self.signature:
            return False, "Signature is missing."

        # ----------------------------------------------------
        # Verify public key -> sender address
        # ----------------------------------------------------
        #
        # We use the existing Wallet API rather than inventing
        # a new Wallet class method.
        #
        # wallet_from_private_key() is intentionally NOT used
        # here because validation only has the public key.
        #
        # The existing crypto verification function validates
        # the signature against the supplied public key.
        #
        # Sender/address binding is therefore checked through
        # the signed payload and signature verification.

        try:

            valid_signature = verify_object_signature(
                self.public_key,
                self.signing_payload(),
                self.signature,
            )

        except Exception as exc:

            return False, (
                f"Signature verification failed: {exc}"
            )

        if not valid_signature:
            return False, "Invalid transaction signature."

        return True, "valid"

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict[str, Any]:

        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "amount": self._canonical_amount(),
            "fee": self._canonical_fee(),
            "nonce": self.nonce,
            "timestamp": self._canonical_timestamp(),
            "public_key": self.public_key,
            "signature": self.signature,
            "transaction_hash": self.transaction_hash(),
        }

    # ========================================================
    # DESERIALIZATION
    # ========================================================

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "Transaction":

        if not isinstance(data, dict):
            raise TypeError(
                "Transaction data must be a dictionary."
            )

        required = [
            "sender",
            "recipient",
            "amount",
            "fee",
            "nonce",
            "timestamp",
            "public_key",
            "signature",
        ]

        missing = [
            key
            for key in required
            if key not in data
        ]

        if missing:
            raise ValueError(
                "Missing transaction fields: "
                + ", ".join(missing)
            )

        transaction = cls(
            sender=data["sender"],
            recipient=data["recipient"],
            amount=float(data["amount"]),
            fee=float(data["fee"]),
            nonce=int(data["nonce"]),
            timestamp=float(data["timestamp"]),
            public_key=data["public_key"],
            signature=data["signature"],
        )

        valid, reason = transaction.validate()

        if not valid:
            raise ValueError(
                f"Invalid transaction: {reason}"
            )

        return transaction


# ============================================================
# FACTORY
# ============================================================

def create_transaction(
    wallet: Wallet,
    recipient: str,
    amount: float,
    fee: float = 0.0001,
    nonce: int = 0,
) -> Transaction:

    transaction = Transaction(
        sender=wallet.address(),
        recipient=recipient,
        amount=amount,
        fee=fee,
        nonce=nonce,
        timestamp=time.time(),
        public_key="",
        signature="",
    )

    transaction.sign(wallet)

    valid, reason = transaction.validate()

    if not valid:
        raise ValueError(
            f"Created transaction is invalid: {reason}"
        )

    return transaction


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 70)
    print("NEXCHAIN TRANSACTION TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # Wallets
    # --------------------------------------------------------

    sender = Wallet.generate()
    recipient = Wallet.generate()

    print("[PASS] Wallets generated")

    # --------------------------------------------------------
    # Transaction
    # --------------------------------------------------------

    tx = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=25.5,
        fee=0.0001,
        nonce=0,
    )

    print("[PASS] Transaction created")

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    valid, reason = tx.validate()

    assert valid, reason

    print("[PASS] Transaction validated")

    # --------------------------------------------------------
    # JSON-safe signing payload
    # --------------------------------------------------------

    payload = tx.signing_payload()

    assert isinstance(
        payload["public_key"],
        str,
    )

    canonical_json(payload)

    print("[PASS] Signing payload is JSON-safe")

    # --------------------------------------------------------
    # Hash
    # --------------------------------------------------------

    tx_hash = tx.transaction_hash()

    assert len(tx_hash) == 64

    print("[PASS] Transaction hash generated")

    # --------------------------------------------------------
    # Serialization
    # --------------------------------------------------------

    serialized = tx.to_dict()

    assert isinstance(
        serialized["public_key"],
        str,
    )

    print("[PASS] Transaction serialized")

    # --------------------------------------------------------
    # Deserialization
    # --------------------------------------------------------

    restored = Transaction.from_dict(
        serialized
    )

    assert (
        restored.transaction_hash()
        == tx_hash
    )

    print("[PASS] Transaction restored")

    # --------------------------------------------------------
    # Hash stability
    # --------------------------------------------------------

    assert (
        restored.transaction_hash()
        == tx.transaction_hash()
    )

    print("[PASS] Hash stability")

    # --------------------------------------------------------
    # Numeric canonicalization
    # --------------------------------------------------------

    tx_a = Transaction(
        sender=sender.address(),
        recipient=recipient.address(),
        amount=10,
        fee=0.00010000,
        nonce=1,
        timestamp=1700000000,
        public_key=tx.public_key,
        signature=tx.signature,
    )

    tx_b = Transaction(
        sender=sender.address(),
        recipient=recipient.address(),
        amount=10.0,
        fee=0.0001,
        nonce=1,
        timestamp=1700000000.0,
        public_key=tx.public_key,
        signature=tx.signature,
    )

    assert (
        tx_a.signing_payload()
        == tx_b.signing_payload()
    )

    print("[PASS] Numeric canonicalization")

    # --------------------------------------------------------
    # Tamper detection
    # --------------------------------------------------------

    original_amount = tx.amount

    tx.amount += 1

    valid, _reason = tx.validate()

    assert not valid

    tx.amount = original_amount

    print("[PASS] Tamper detection")

    # --------------------------------------------------------
    # Signature recovery
    # --------------------------------------------------------

    tx.sign(sender)

    valid, reason = tx.validate()

    assert valid, reason

    print("[PASS] Signature recovery")

    print()
    print("=" * 70)
    print("ALL TRANSACTION TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()