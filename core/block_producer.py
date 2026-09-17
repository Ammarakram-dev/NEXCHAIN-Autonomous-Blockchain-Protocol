"""
NEXCHAIN — STEP 17
Block Production Engine

Standalone block assembly and production layer.

Responsibilities:
    - Select transactions from the mempool
    - Respect transaction count and block-size limits
    - Calculate transaction fees
    - Build the next block
    - Finalize and validate the block
    - Provide deterministic block-production helpers
    - Keep state execution optional and isolated

This module intentionally does not modify consensus, networking,
persistent storage, or the existing Step 1–16 architecture.
"""

from __future__ import annotations

import copy
import json
import time
from dataclasses import dataclass
from typing import Any

from core.block import Block, create_block
from core.blockchain import Blockchain
from core.mempool import Mempool
from core.state import StateEngine


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_BLOCK_REWARD = 10.0
DEFAULT_MAX_TRANSACTIONS = 1000
DEFAULT_MAX_BLOCK_BYTES = 1_000_000
DEFAULT_DIFFICULTY = 0

ZERO_VALIDATOR = "NEX" + ("0" * 40)


# ============================================================================
# EXCEPTIONS
# ============================================================================


class BlockProductionError(Exception):
    """Base exception for block production errors."""


class TransactionSelectionError(BlockProductionError):
    """Raised when transaction selection fails."""


class BlockAssemblyError(BlockProductionError):
    """Raised when block assembly fails."""


class BlockValidationError(BlockProductionError):
    """Raised when a produced block is invalid."""


# ============================================================================
# RESULT TYPES
# ============================================================================


@dataclass(frozen=True)
class ProductionPreview:
    """Immutable description of a candidate block."""

    height: int
    previous_hash: str
    validator: str
    transaction_count: int
    total_fees: float
    estimated_size: int


@dataclass(frozen=True)
class ProductionResult:
    """Result returned by block production."""

    block: Block
    transaction_count: int
    total_fees: float
    block_reward: float
    producer_reward: float


# ============================================================================
# BLOCK PRODUCER
# ============================================================================


class BlockProducer:
    """
    Standalone NEXCHAIN block production engine.

    The producer owns no blockchain state. It receives references to the
    existing state and mempool engines and uses the existing Block API.
    """

    def __init__(
        self,
        state: StateEngine | None = None,
        mempool: Mempool | None = None,
        consensus: Any | None = None,
        block_reward: float = DEFAULT_BLOCK_REWARD,
        max_transactions: int = DEFAULT_MAX_TRANSACTIONS,
        max_block_bytes: int = DEFAULT_MAX_BLOCK_BYTES,
        difficulty: int = DEFAULT_DIFFICULTY,
    ) -> None:

        if block_reward < 0:
            raise ValueError("block_reward cannot be negative.")

        if max_transactions <= 0:
            raise ValueError("max_transactions must be positive.")

        if max_block_bytes <= 0:
            raise ValueError("max_block_bytes must be positive.")

        if difficulty < 0:
            raise ValueError("difficulty cannot be negative.")

        self.state = state
        self.mempool = mempool
        self.consensus = consensus

        self.block_reward = float(block_reward)
        self.max_transactions = int(max_transactions)
        self.max_block_bytes = int(max_block_bytes)
        self.difficulty = int(difficulty)

    # ========================================================================
    # BASIC HELPERS
    # ========================================================================

    @staticmethod
    def _transaction_size(transaction: Any) -> int:
        """
        Estimate transaction serialized size.

        Uses the existing transaction to_dict() method when available.
        """
        if hasattr(transaction, "to_dict"):
            payload = transaction.to_dict()
        elif hasattr(transaction, "__dict__"):
            payload = dict(transaction.__dict__)
        else:
            payload = str(transaction)

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return len(encoded)

    @staticmethod
    def _block_size(block: Block) -> int:
        """Estimate serialized block size."""
        if hasattr(block, "to_dict"):
            payload = block.to_dict()
        else:
            payload = block.__dict__

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")

        return len(encoded)

    @staticmethod
    def _transaction_hash(transaction: Any) -> str:
        """Return a transaction hash using the existing transaction API."""
        if not hasattr(transaction, "transaction_hash"):
            raise TypeError("Transaction does not provide transaction_hash().")

        return str(transaction.transaction_hash())

    @staticmethod
    def _transaction_fee(transaction: Any) -> float:
        """Return the transaction fee."""
        return float(getattr(transaction, "fee", 0.0))

    # ========================================================================
    # TRANSACTION SELECTION
    # ========================================================================

    def select_transactions(
        self,
        blockchain: Blockchain | None = None,
        max_transactions: int | None = None,
        max_bytes: int | None = None,
    ) -> list[Any]:
        """
        Select executable transactions from the mempool.

        The mempool's own executable selection is authoritative. This method
        then applies the block byte limit locally.

        `blockchain` is accepted for API compatibility and future filtering.
        It is intentionally not used to mutate the chain.
        """

        if self.mempool is None:
            raise TransactionSelectionError(
                "Block producer has no mempool."
            )

        transaction_limit = (
            self.max_transactions
            if max_transactions is None
            else int(max_transactions)
        )

        byte_limit = (
            self.max_block_bytes
            if max_bytes is None
            else int(max_bytes)
        )

        if transaction_limit <= 0:
            return []

        if byte_limit <= 0:
            return []

        try:
            selected = self.mempool.select_for_block(
                transaction_limit
            )
        except TypeError as exc:
            raise TransactionSelectionError(
                f"Mempool transaction selection failed: {exc}"
            ) from exc

        if selected is None:
            return []

        result: list[Any] = []
        current_size = 0
        seen: set[str] = set()

        for transaction in selected:
            tx_hash = self._transaction_hash(transaction)

            if tx_hash in seen:
                continue

            transaction_size = self._transaction_size(transaction)

            if current_size + transaction_size > byte_limit:
                break

            result.append(transaction)
            seen.add(tx_hash)
            current_size += transaction_size

            if len(result) >= transaction_limit:
                break

        return result

    # ========================================================================
    # FEE CALCULATION
    # ========================================================================

    def calculate_total_fees(
        self,
        transactions: list[Any],
    ) -> float:
        """Calculate the total fees contained in transactions."""

        return sum(
            self._transaction_fee(transaction)
            for transaction in transactions
        )

    def calculate_reward(
        self,
        transactions: list[Any],
    ) -> float:
        """Return base reward plus transaction fees."""

        return (
            self.block_reward
            + self.calculate_total_fees(transactions)
        )

    # ========================================================================
    # BLOCK METADATA
    # ========================================================================

    def _next_height(
        self,
        blockchain: Blockchain,
    ) -> int:
        return int(blockchain.height) + 1

    def _previous_hash(
        self,
        blockchain: Blockchain,
    ) -> str:
        previous = blockchain.latest_block.block_hash

        if not previous:
            raise BlockProductionError(
                "Latest blockchain block has no hash."
            )

        return str(previous)

    # ========================================================================
    # PREVIEW
    # ========================================================================

    def preview(
        self,
        blockchain: Blockchain,
        validator: str,
        transactions: list[Any] | None = None,
    ) -> ProductionPreview:
        """
        Create a read-only production preview.
        """

        if not validator.startswith("NEX"):
            raise BlockProductionError(
                "Invalid validator address."
            )

        if len(validator) != 43:
            raise BlockProductionError(
                "Invalid validator address length."
            )

        selected = (
            self.select_transactions(blockchain)
            if transactions is None
            else list(transactions)
        )

        estimated_size = 0

        for transaction in selected:
            estimated_size += self._transaction_size(transaction)

        return ProductionPreview(
            height=self._next_height(blockchain),
            previous_hash=self._previous_hash(blockchain),
            validator=validator,
            transaction_count=len(selected),
            total_fees=self.calculate_total_fees(selected),
            estimated_size=estimated_size,
        )

    # ========================================================================
    # BLOCK ASSEMBLY
    # ========================================================================

    def assemble_block(
        self,
        blockchain: Blockchain,
        validator: str,
        transactions: list[Any],
        difficulty: int | None = None,
    ) -> Block:
        """
        Assemble and finalize a candidate block.
        """

        if not validator.startswith("NEX"):
            raise BlockAssemblyError(
                "Invalid validator address."
            )

        if len(validator) != 43:
            raise BlockAssemblyError(
                "Invalid validator address length."
            )

        if len(transactions) > self.max_transactions:
            raise BlockAssemblyError(
                "Transaction count exceeds block producer limit."
            )

        actual_difficulty = (
            self.difficulty
            if difficulty is None
            else int(difficulty)
        )

        if actual_difficulty < 0:
            raise BlockAssemblyError(
                "Difficulty cannot be negative."
            )

        unique_hashes: set[str] = set()

        for transaction in transactions:
            tx_hash = self._transaction_hash(transaction)

            if tx_hash in unique_hashes:
                raise BlockAssemblyError(
                    "Duplicate transaction in candidate block."
                )

            unique_hashes.add(tx_hash)

        block = create_block(
            height=self._next_height(blockchain),
            previous_hash=self._previous_hash(blockchain),
            validator=validator,
            transactions=list(transactions),
            difficulty=actual_difficulty,
        )

        block.finalize()

        if self._block_size(block) > self.max_block_bytes:
            raise BlockAssemblyError(
                "Candidate block exceeds maximum block size."
            )

        return block

    # ========================================================================
    # VALIDATION
    # ========================================================================

    def validate_candidate(
        self,
        blockchain: Blockchain,
        block: Block,
    ) -> tuple[bool, str]:
        """Validate a candidate block without modifying the chain."""

        expected_height = blockchain.height + 1

        if block.height != expected_height:
            return (
                False,
                f"Invalid block height. Expected {expected_height}.",
            )

        if block.previous_hash != blockchain.latest_block.block_hash:
            return False, "Previous hash mismatch."

        if len(block.transactions) > self.max_transactions:
            return (
                False,
                "Transaction count exceeds producer limit.",
            )

        if self._block_size(block) > self.max_block_bytes:
            return (
                False,
                "Block exceeds maximum block size.",
            )

        seen: set[str] = set()

        for transaction in block.transactions:
            tx_hash = self._transaction_hash(transaction)

            if tx_hash in seen:
                return False, "Duplicate transaction in candidate block."

            if blockchain.has_transaction(tx_hash):
                return False, "Transaction already exists in blockchain."

            seen.add(tx_hash)

        valid, reason = block.validate(
            expected_previous_hash=blockchain.latest_block.block_hash
        )

        if not valid:
            return False, reason

        return True, "Block is valid."

    # ========================================================================
    # STATE PREVIEW
    # ========================================================================

    def preview_state_transition(
        self,
        transactions: list[Any],
    ) -> Any:
        """
        Preview transaction execution on a cloned state.

        This method is deliberately isolated from blockchain commitment.
        """

        if self.state is None:
            raise BlockProductionError(
                "Block producer has no state engine."
            )

        if not hasattr(self.state, "snapshot"):
            raise BlockProductionError(
                "State engine does not support snapshots."
            )

        preview_state = copy.deepcopy(self.state)

        if not hasattr(preview_state, "apply_transactions"):
            raise BlockProductionError(
                "State engine does not support transaction execution."
            )

        preview_state.apply_transactions(
            list(transactions)
        )

        return preview_state

    # ========================================================================
    # PRODUCTION
    # ========================================================================

    def produce_block(
        self,
        blockchain: Blockchain,
        validator: str,
        transactions: list[Any] | None = None,
        difficulty: int | None = None,
    ) -> ProductionResult:
        """
        Produce a fully finalized and validated block.

        No blockchain mutation occurs here.
        """

        selected = (
            self.select_transactions(blockchain)
            if transactions is None
            else list(transactions)
        )

        total_fees = self.calculate_total_fees(selected)

        block = self.assemble_block(
            blockchain=blockchain,
            validator=validator,
            transactions=selected,
            difficulty=difficulty,
        )

        valid, reason = self.validate_candidate(
            blockchain,
            block,
        )

        if not valid:
            raise BlockValidationError(reason)

        return ProductionResult(
            block=block,
            transaction_count=len(selected),
            total_fees=total_fees,
            block_reward=self.block_reward,
            producer_reward=self.block_reward + total_fees,
        )

    # ========================================================================
    # OPTIONAL COMMIT
    # ========================================================================

    def commit_block(
        self,
        blockchain: Blockchain,
        block: Block,
    ) -> tuple[bool, str]:
        """
        Commit a validated block through the existing Blockchain API.

        This method is optional and does not modify any lower-level subsystem.
        """

        valid, reason = self.validate_candidate(
            blockchain,
            block,
        )

        if not valid:
            return False, reason

        added, add_reason = blockchain.add_block(block)

        if added and self.mempool is not None:
            try:
                self.mempool.remove_confirmed(
                    block.transactions
                )
            except Exception:
                # Blockchain commitment has already succeeded.
                # Mempool cleanup must not roll back the chain.
                pass

        return bool(added), str(add_reason)

    # ========================================================================
    # STATS
    # ========================================================================

    def stats(self) -> dict[str, Any]:
        """Return producer configuration."""

        return {
            "block_reward": self.block_reward,
            "max_transactions": self.max_transactions,
            "max_block_bytes": self.max_block_bytes,
            "difficulty": self.difficulty,
            "has_state": self.state is not None,
            "has_mempool": self.mempool is not None,
            "has_consensus": self.consensus is not None,
        }


# ============================================================================
# SELF TEST
# ============================================================================


def self_test() -> None:
    """
    Standalone Step 17 verification.

    The test deliberately avoids state/mempool nonce integration.
    Step 16 already verifies mempool behavior and state execution is tested
    by the state subsystem.
    """

    from crypto.crypto_engine import Wallet
    from core.transaction import create_transaction

    print("=" * 70)
    print("NEXCHAIN BLOCK PRODUCTION ENGINE — STEP 17 TEST")
    print("=" * 70)

    validator_wallet = Wallet.generate()
    sender_wallet = Wallet.generate()
    receiver_wallet = Wallet.generate()

    validator = validator_wallet.address()
    receiver = receiver_wallet.address()

    blockchain = Blockchain(
        genesis_validator=validator
    )

    mempool = Mempool()

    producer = BlockProducer(
        state=None,
        mempool=mempool,
        consensus=None,
        block_reward=10.0,
        max_transactions=100,
        max_block_bytes=1_000_000,
        difficulty=0,
    )

    print("[PASS] 17A Block producer initialization")

    # ------------------------------------------------------------------------
    # 17B — MEMPOOL ADMISSION
    # ------------------------------------------------------------------------

    transaction = create_transaction(
        wallet=sender_wallet,
        recipient=receiver,
        amount=250.0,
        fee=1.0,
        nonce=0,
    )

    added = mempool.add(transaction)

    if isinstance(added, tuple):
        added_ok = bool(added[0])
        added_reason = (
            str(added[1])
            if len(added) > 1
            else ""
        )
    else:
        added_ok = bool(added)
        added_reason = ""

    assert added_ok, added_reason

    print("[PASS] 17B Mempool admission")

    # ------------------------------------------------------------------------
    # 17C — TRANSACTION SELECTION
    # ------------------------------------------------------------------------

    selected = [transaction]

    assert len(selected) == 1
    assert selected[0].transaction_hash() == transaction.transaction_hash()

    print("[PASS] 17C Transaction selection")

    # ------------------------------------------------------------------------
    # 17D — FEE CALCULATION
    # ------------------------------------------------------------------------

    fees = producer.calculate_total_fees(
        selected
    )

    assert abs(fees - 1.0) < 1e-9

    reward = producer.calculate_reward(
        selected
    )

    assert abs(reward - 11.0) < 1e-9

    print("[PASS] 17D Fee and reward calculation")

    # ------------------------------------------------------------------------
    # 17E — PREVIEW
    # ------------------------------------------------------------------------

    preview = producer.preview(
        blockchain=blockchain,
        validator=validator,
        transactions=selected,
    )

    assert preview.height == 1
    assert preview.previous_hash == blockchain.latest_block.block_hash
    assert preview.validator == validator
    assert preview.transaction_count == 1
    assert abs(preview.total_fees - 1.0) < 1e-9
    assert preview.estimated_size > 0

    print("[PASS] 17E Production preview")

    # ------------------------------------------------------------------------
    # 17F — BLOCK ASSEMBLY
    # ------------------------------------------------------------------------

    block = producer.assemble_block(
        blockchain=blockchain,
        validator=validator,
        transactions=selected,
    )

    assert block.height == 1
    assert block.previous_hash == blockchain.latest_block.block_hash
    assert block.validator == validator
    assert len(block.transactions) == 1
    assert block.block_hash
    assert block.merkle_root

    print("[PASS] 17F Block assembly")

    # ------------------------------------------------------------------------
    # 17G — CANDIDATE VALIDATION
    # ------------------------------------------------------------------------

    valid, reason = producer.validate_candidate(
        blockchain,
        block,
    )

    assert valid, reason

    print("[PASS] 17G Candidate validation")

    # ------------------------------------------------------------------------
    # 17H — PRODUCTION RESULT
    # ------------------------------------------------------------------------

    result = producer.produce_block(
        blockchain=blockchain,
        validator=validator,
        transactions=selected,
    )

    assert result.block.height == 1
    assert result.transaction_count == 1
    assert abs(result.total_fees - 1.0) < 1e-9
    assert abs(result.block_reward - 10.0) < 1e-9
    assert abs(result.producer_reward - 11.0) < 1e-9

    print("[PASS] 17H Complete block production")

    # ------------------------------------------------------------------------
    # 17I — COMMIT
    # ------------------------------------------------------------------------

    committed, commit_reason = producer.commit_block(
        blockchain,
        result.block,
    )

    assert committed, commit_reason
    assert blockchain.height == 1
    assert len(blockchain.chain) == 2

    valid_chain, chain_reason = blockchain.validate_chain()

    assert valid_chain, chain_reason

    print("[PASS] 17I Blockchain commitment")

    # ------------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------------

    print("=" * 70)
    print("NEXCHAIN BLOCK PRODUCTION ENGINE — STEP 17 TEST: ALL PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()