"""
NEXCHAIN Block Engine
=====================

Defines the fundamental block structure of NEXCHAIN.

A block contains:
    - Header metadata
    - Previous block reference
    - Merkle root
    - State root
    - Transactions
    - Cryptographic block hash

The implementation is deterministic so every node can
independently verify the same block.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from crypto.crypto_engine import hash_object
from core.merkle import MerkleTree
from core.transaction import Transaction


# ============================================================
# CONSTANTS
# ============================================================

GENESIS_PREVIOUS_HASH = "0" * 64
CURRENT_VERSION = 1


# ============================================================
# BLOCK
# ============================================================

@dataclass
class Block:

    version: int
    height: int
    previous_hash: str
    timestamp: float
    validator: str
    nonce: int
    difficulty: int
    transactions: list[Transaction] = field(default_factory=list)

    merkle_root: str = ""
    block_hash: str = ""
    state_root: str = ""

    # ========================================================
    # MERKLE ROOT
    # ========================================================

    def calculate_merkle_root(self) -> str:
        """Calculate the Merkle root from all transactions."""

        if not self.transactions:
            return hash_object({"empty": True})

        transaction_hashes = [
            transaction.transaction_hash()
            for transaction in self.transactions
        ]

        tree = MerkleTree(transaction_hashes)

        return tree.get_root()

    # ========================================================
    # HEADER
    # ========================================================

    def header(self) -> dict[str, Any]:
        """
        Return the deterministic block header.

        state_root is included in the header and therefore
        cryptographically committed by the block hash.
        """

        return {
            "version": self.version,
            "height": self.height,
            "previous_hash": self.previous_hash,
            "merkle_root": self.merkle_root,
            "state_root": self.state_root,
            "timestamp": self.timestamp,
            "validator": self.validator,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
        }

    # ========================================================
    # HASH
    # ========================================================

    def calculate_hash(self) -> str:
        """Calculate the block hash from the complete header."""

        return hash_object(self.header())

    # ========================================================
    # FINALIZE
    # ========================================================

    def finalize(self) -> None:
        """Calculate the Merkle root and block hash."""

        self.merkle_root = self.calculate_merkle_root()
        self.block_hash = self.calculate_hash()

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate(
        self,
        expected_previous_hash: str | None = None,
    ) -> tuple[bool, str]:
        """
        Validate the complete block.

        Checks:
            - version
            - height
            - previous hash
            - timestamp
            - validator
            - nonce
            - difficulty
            - state root
            - transactions
            - Merkle root
            - block hash
            - proof target
        """

        # ----------------------------------------------------
        # Version
        # ----------------------------------------------------

        if self.version != CURRENT_VERSION:
            return False, "Unsupported block version."

        # ----------------------------------------------------
        # Height
        # ----------------------------------------------------

        if self.height < 0:
            return False, "Invalid block height."

        # ----------------------------------------------------
        # Previous hash
        # ----------------------------------------------------

        if (
            not isinstance(self.previous_hash, str)
            or len(self.previous_hash) != 64
        ):
            return False, "Invalid previous block hash."

        if expected_previous_hash is not None:
            if self.previous_hash != expected_previous_hash:
                return False, "Previous hash does not match chain."

        # ----------------------------------------------------
        # Timestamp
        # ----------------------------------------------------

        if self.timestamp <= 0:
            return False, "Invalid timestamp."

        if self.timestamp > time.time() + 300:
            return False, "Block timestamp is too far in the future."

        # ----------------------------------------------------
        # Validator
        # ----------------------------------------------------

        if not isinstance(self.validator, str):
            return False, "Invalid validator."

        if not self.validator.startswith("NEX"):
            return False, "Invalid validator address."

        if len(self.validator) != 43:
            return False, "Invalid validator address length."

        # ----------------------------------------------------
        # Nonce
        # ----------------------------------------------------

        if not isinstance(self.nonce, int) or self.nonce < 0:
            return False, "Invalid nonce."

        # ----------------------------------------------------
        # Difficulty
        # ----------------------------------------------------

        if not isinstance(self.difficulty, int):
            return False, "Invalid difficulty."

        if self.difficulty < 0 or self.difficulty > 64:
            return False, "Invalid difficulty."

        # ----------------------------------------------------
        # State Root
        # ----------------------------------------------------

        if not isinstance(self.state_root, str):
            return False, "Invalid state root."

        # Empty state roots remain valid for backward
        # compatibility with blocks created before state
        # integration.

        if self.state_root:

            if len(self.state_root) != 64:
                return False, "Invalid state root length."

            if any(
                character not in "0123456789abcdefABCDEF"
                for character in self.state_root
            ):
                return False, "Invalid state root format."

        # ----------------------------------------------------
        # Transactions
        # ----------------------------------------------------

        for transaction in self.transactions:

            valid, reason = transaction.validate()

            if not valid:
                return False, f"Invalid transaction: {reason}"

        # ----------------------------------------------------
        # Merkle root
        # ----------------------------------------------------

        calculated_merkle = self.calculate_merkle_root()

        if self.merkle_root != calculated_merkle:
            return False, "Merkle root mismatch."

        # ----------------------------------------------------
        # Block hash
        # ----------------------------------------------------

        calculated_hash = self.calculate_hash()

        if self.block_hash != calculated_hash:
            return False, "Block hash mismatch."

        # ----------------------------------------------------
        # Proof target
        # ----------------------------------------------------

        if self.difficulty > 0:

            target_prefix = "0" * self.difficulty

            if not self.block_hash.startswith(target_prefix):
                return False, "Block does not satisfy difficulty target."

        return True, "valid"

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict[str, Any]:
        """Convert the complete block to a dictionary."""

        return {
            "version": self.version,
            "height": self.height,
            "previous_hash": self.previous_hash,
            "timestamp": self.timestamp,
            "validator": self.validator,
            "nonce": self.nonce,
            "difficulty": self.difficulty,
            "merkle_root": self.merkle_root,
            "state_root": self.state_root,
            "block_hash": self.block_hash,
            "transactions": [
                transaction.to_dict()
                for transaction in self.transactions
            ],
        }

    # ========================================================
    # DESERIALIZATION
    # ========================================================

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Block":
        """Reconstruct a block from serialized data."""

        transactions = [
            Transaction.from_dict(item)
            for item in data.get("transactions", [])
        ]

        return cls(
            version=int(data["version"]),
            height=int(data["height"]),
            previous_hash=data["previous_hash"],
            timestamp=float(data["timestamp"]),
            validator=data["validator"],
            nonce=int(data["nonce"]),
            difficulty=int(data["difficulty"]),
            transactions=transactions,
            merkle_root=data.get("merkle_root", ""),
            block_hash=data.get("block_hash", ""),
            state_root=data.get("state_root", ""),
        )


# ============================================================
# BLOCK FACTORY
# ============================================================

def create_block(
    height: int,
    previous_hash: str,
    validator: str,
    transactions: list[Transaction],
    difficulty: int = 0,
    state_root: str = "",
) -> Block:
    """
    Construct and finalize a NEXCHAIN block.

    state_root represents the resulting global state after
    applying this block's transactions.
    """

    block = Block(
        version=CURRENT_VERSION,
        height=height,
        previous_hash=previous_hash,
        timestamp=time.time(),
        validator=validator,
        nonce=0,
        difficulty=difficulty,
        transactions=transactions,
        state_root=state_root,
    )

    block.finalize()

    return block


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 60)
    print("NEXCHAIN BLOCK ENGINE TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Wallets
    # --------------------------------------------------------

    from crypto.crypto_engine import Wallet
    from core.transaction import create_transaction

    sender = Wallet.generate()
    recipient = Wallet.generate()

    # --------------------------------------------------------
    # Signed transaction
    # --------------------------------------------------------

    transaction = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=100,
        fee=0.01,
        nonce=0,
    )

    # --------------------------------------------------------
    # Deterministic test state root
    # --------------------------------------------------------

    state_root = hash_object(
        {
            "alice": 899.99,
            "bob": 100.0,
        }
    )

    # --------------------------------------------------------
    # Block
    # --------------------------------------------------------

    block = create_block(
        height=1,
        previous_hash=GENESIS_PREVIOUS_HASH,
        validator=sender.address(),
        transactions=[transaction],
        difficulty=0,
        state_root=state_root,
    )

    print()
    print(f"Height:       {block.height}")
    print(f"Previous:     {block.previous_hash}")
    print(f"Merkle Root:  {block.merkle_root}")
    print(f"State Root:   {block.state_root}")
    print(f"Block Hash:   {block.block_hash}")

    # --------------------------------------------------------
    # Validation
    # --------------------------------------------------------

    valid, reason = block.validate()

    assert valid, reason

    print()
    print("[PASS] Block creation")
    print("[PASS] Merkle root integration")
    print("[PASS] State root integration")
    print("[PASS] Block hashing")
    print("[PASS] Block validation")

    # --------------------------------------------------------
    # State root tampering
    # --------------------------------------------------------

    original_state_root = block.state_root

    block.state_root = "a" * 64

    valid, reason = block.validate()

    assert not valid
    assert reason == "Block hash mismatch."

    print("[PASS] State root tampering detection")

    block.state_root = original_state_root

    # --------------------------------------------------------
    # Transaction tampering
    # --------------------------------------------------------

    transaction.amount = 999999

    valid, reason = block.validate()

    assert not valid

    print("[PASS] Transaction tampering detection")

    # --------------------------------------------------------
    # Restore with a fresh signed transaction
    # --------------------------------------------------------

    restored_transaction = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=100,
        fee=0.01,
        nonce=0,
    )

    block.transactions = [restored_transaction]
    block.finalize()

    valid, reason = block.validate()

    assert valid, reason

    # --------------------------------------------------------
    # Serialization / deserialization
    # --------------------------------------------------------

    serialization_transaction = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=100,
        fee=0.01,
        nonce=0,
    )

    serialization_block = create_block(
        height=1,
        previous_hash=GENESIS_PREVIOUS_HASH,
        validator=sender.address(),
        transactions=[serialization_transaction],
        difficulty=0,
        state_root=state_root,
    )

    serialized = serialization_block.to_dict()

    restored = Block.from_dict(serialized)

    valid, reason = restored.validate()

    assert valid, reason
    assert restored.state_root == serialization_block.state_root
    assert restored.block_hash == serialization_block.block_hash
    assert (
        restored.merkle_root
        == serialization_block.merkle_root
    )

    print("[PASS] State root serialization")
    print("[PASS] Block deserialization")

    # --------------------------------------------------------
    # Block hash tampering
    # --------------------------------------------------------

    block.block_hash = "f" * 64

    valid, reason = block.validate()

    assert not valid

    print("[PASS] Block hash tampering detection")

    # --------------------------------------------------------
    # Final success
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("ALL BLOCK TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    self_test()