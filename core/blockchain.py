"""
NEXCHAIN Blockchain Engine
==========================

Maintains the canonical chain of NEXCHAIN blocks.

Responsibilities:
    - Genesis block creation
    - Block insertion
    - Chain linking
    - Transaction uniqueness
    - Complete chain validation
    - Serialization
"""

from __future__ import annotations

import time
from typing import Any

from core.block import (
    Block,
    CURRENT_VERSION,
    GENESIS_PREVIOUS_HASH,
    create_block,
)
from core.transaction import Transaction


# ============================================================
# BLOCKCHAIN
# ============================================================

class Blockchain:

    def __init__(self, genesis_validator: str):

        if not genesis_validator.startswith("NEX"):
            raise ValueError("Invalid genesis validator.")

        if len(genesis_validator) != 43:
            raise ValueError("Invalid genesis validator length.")

        self.genesis_validator = genesis_validator

        self.chain: list[Block] = []

        self.transaction_index: set[str] = set()

        self._create_genesis_block()

    # ========================================================
    # GENESIS
    # ========================================================

    def _create_genesis_block(self) -> None:
        """
        Create the immutable genesis block.
        """

        genesis = Block(
            version=CURRENT_VERSION,
            height=0,
            previous_hash=GENESIS_PREVIOUS_HASH,
            timestamp=1700000000.0,
            validator=self.genesis_validator,
            nonce=0,
            difficulty=0,
            transactions=[],
        )

        genesis.finalize()

        valid, reason = genesis.validate()

        if not valid:
            raise RuntimeError(
                f"Genesis block creation failed: {reason}"
            )

        self.chain.append(genesis)

    # ========================================================
    # PROPERTIES
    # ========================================================

    @property
    def height(self) -> int:
        """
        Return current chain height.
        """

        return self.chain[-1].height

    @property
    def latest_block(self) -> Block:
        """
        Return the latest block.
        """

        return self.chain[-1]

    # ========================================================
    # TRANSACTION INDEX
    # ========================================================

    def _index_transactions(self, block: Block) -> None:

        for transaction in block.transactions:

            self.transaction_index.add(
                transaction.transaction_hash()
            )

    # ========================================================
    # TRANSACTION CHECK
    # ========================================================

    def has_transaction(self, transaction_hash: str) -> bool:

        return transaction_hash in self.transaction_index

    # ========================================================
    # ADD BLOCK
    # ========================================================

    def add_block(self, block: Block) -> tuple[bool, str]:
        """
        Validate and append a block to the chain.
        """

        # ----------------------------------------------------
        # Height
        # ----------------------------------------------------

        expected_height = self.height + 1

        if block.height != expected_height:
            return False, (
                f"Invalid block height. "
                f"Expected {expected_height}."
            )

        # ----------------------------------------------------
        # Previous hash
        # ----------------------------------------------------

        expected_previous = self.latest_block.block_hash

        if block.previous_hash != expected_previous:
            return False, "Previous hash mismatch."

        # ----------------------------------------------------
        # Duplicate transactions
        # ----------------------------------------------------

        for transaction in block.transactions:

            tx_hash = transaction.transaction_hash()

            if tx_hash in self.transaction_index:
                return False, "Duplicate transaction detected."

        # ----------------------------------------------------
        # Block validation
        # ----------------------------------------------------

        valid, reason = block.validate(
            expected_previous_hash=expected_previous
        )

        if not valid:
            return False, reason

        # ----------------------------------------------------
        # Append
        # ----------------------------------------------------

        self.chain.append(block)

        self._index_transactions(block)

        return True, "Block added."

    # ========================================================
    # CREATE NEXT BLOCK
    # ========================================================

    def create_next_block(
        self,
        validator: str,
        transactions: list[Transaction],
        difficulty: int = 0,
    ) -> Block:
        """
        Create the next block without automatically adding it.
        """

        return create_block(
            height=self.height + 1,
            previous_hash=self.latest_block.block_hash,
            validator=validator,
            transactions=transactions,
            difficulty=difficulty,
        )

    # ========================================================
    # VALIDATE COMPLETE CHAIN
    # ========================================================

    def validate_chain(self) -> tuple[bool, str]:
        """
        Validate every block and every link in the chain.
        """

        if not self.chain:
            return False, "Blockchain is empty."

        # ----------------------------------------------------
        # Genesis
        # ----------------------------------------------------

        genesis = self.chain[0]

        if genesis.height != 0:
            return False, "Genesis height is invalid."

        if genesis.previous_hash != GENESIS_PREVIOUS_HASH:
            return False, "Genesis previous hash is invalid."

        # ----------------------------------------------------
        # Block-by-block validation
        # ----------------------------------------------------

        seen_transactions: set[str] = set()

        for index, block in enumerate(self.chain):

            # Height
            if block.height != index:
                return False, (
                    f"Invalid height at block {index}."
                )

            # Previous link
            if index > 0:

                previous = self.chain[index - 1]

                if block.previous_hash != previous.block_hash:
                    return False, (
                        f"Broken chain link at block {index}."
                    )

            # Block itself
            valid, reason = block.validate()

            if not valid:
                return False, (
                    f"Block {index} invalid: {reason}"
                )

            # Transaction uniqueness
            for transaction in block.transactions:

                tx_hash = transaction.transaction_hash()

                if tx_hash in seen_transactions:
                    return False, (
                        f"Duplicate transaction at block {index}."
                    )

                seen_transactions.add(tx_hash)

        return True, "Chain is valid."

    # ========================================================
    # FIND TRANSACTION
    # ========================================================

    def find_transaction(
        self,
        transaction_hash: str,
    ) -> tuple[int, Transaction] | None:

        for block in self.chain:

            for transaction in block.transactions:

                if transaction.transaction_hash() == transaction_hash:

                    return block.height, transaction

        return None

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict[str, Any]:

        return {
            "genesis_validator": self.genesis_validator,
            "height": self.height,
            "blocks": [
                block.to_dict()
                for block in self.chain
            ],
        }

    # ========================================================
    # STATS
    # ========================================================

    def stats(self) -> dict[str, Any]:

        transaction_count = sum(
            len(block.transactions)
            for block in self.chain
        )

        return {
            "height": self.height,
            "blocks": len(self.chain),
            "transactions": transaction_count,
            "latest_hash": self.latest_block.block_hash,
        }


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    from crypto.crypto_engine import Wallet
    from core.transaction import create_transaction

    print("=" * 60)
    print("NEXCHAIN BLOCKCHAIN ENGINE TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Wallets
    # --------------------------------------------------------

    validator = Wallet.generate()
    sender = Wallet.generate()
    recipient = Wallet.generate()

    # --------------------------------------------------------
    # Blockchain
    # --------------------------------------------------------

    blockchain = Blockchain(
        genesis_validator=validator.address()
    )

    assert blockchain.height == 0

    print()
    print("[PASS] Genesis block created")
    print(f"       Genesis hash: {blockchain.latest_block.block_hash}")

    # --------------------------------------------------------
    # Transaction
    # --------------------------------------------------------

    transaction = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=50,
        fee=0.01,
        nonce=0,
    )

    # --------------------------------------------------------
    # Block 1
    # --------------------------------------------------------

    block1 = blockchain.create_next_block(
        validator=validator.address(),
        transactions=[transaction],
    )

    added, reason = blockchain.add_block(block1)

    assert added, reason

    print("[PASS] Block 1 added")

    # --------------------------------------------------------
    # Block 2
    # --------------------------------------------------------

    transaction2 = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=25,
        fee=0.01,
        nonce=1,
    )

    block2 = blockchain.create_next_block(
        validator=validator.address(),
        transactions=[transaction2],
    )

    added, reason = blockchain.add_block(block2)

    assert added, reason

    print("[PASS] Block 2 added")

    # --------------------------------------------------------
    # Chain validation
    # --------------------------------------------------------

    valid, reason = blockchain.validate_chain()

    assert valid, reason

    print("[PASS] Complete chain validation")

    # --------------------------------------------------------
    # Height
    # --------------------------------------------------------

    assert blockchain.height == 2

    print("[PASS] Sequential block heights")

    # --------------------------------------------------------
    # Transaction lookup
    # --------------------------------------------------------

    result = blockchain.find_transaction(
        transaction.transaction_hash()
    )

    assert result is not None
    assert result[0] == 1

    print("[PASS] Transaction lookup")

    # --------------------------------------------------------
    # Duplicate transaction test
    # --------------------------------------------------------

    duplicate_block = blockchain.create_next_block(
        validator=validator.address(),
        transactions=[transaction],
    )

    added, reason = blockchain.add_block(
        duplicate_block
    )

    assert not added

    print("[PASS] Duplicate transaction prevention")

    # --------------------------------------------------------
    # Tamper chain
    # --------------------------------------------------------

    original_hash = blockchain.chain[1].block_hash

    blockchain.chain[1].block_hash = "f" * 64

    valid, reason = blockchain.validate_chain()

    assert not valid

    print("[PASS] Chain tamper detection")

    blockchain.chain[1].block_hash = original_hash

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    valid, reason = blockchain.validate_chain()

    assert valid

    print("[PASS] Chain restored successfully")

    print()
    print("Blockchain statistics:")
    print(blockchain.stats())

    print()
    print("=" * 60)
    print("ALL BLOCKCHAIN TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    self_test()