"""
NEXCHAIN Consensus-Blockchain Integration
=========================================

Connects the NEXCHAIN consensus engine with the blockchain core.

Flow:

    Validators
        ↓
    Consensus scoring
        ↓
    Deterministic proposer selection
        ↓
    Candidate block
        ↓
    Consensus validation
        ↓
    Blockchain validation
        ↓
    Block commitment
"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional, Tuple

from consensus.engine import ConsensusEngine, Validator
from core.block import Block
from core.blockchain import Blockchain


# ============================================================
# GENESIS CONFIGURATION
# ============================================================

GENESIS_VALIDATOR = "NEX" + ("0" * 40)

assert len(GENESIS_VALIDATOR) == 43
assert GENESIS_VALIDATOR.startswith("NEX")


class ConsensusBlockchain:
    """
    Consensus-aware blockchain coordinator.
    """

    def __init__(
        self,
        blockchain: Optional[Blockchain] = None,
        consensus: Optional[ConsensusEngine] = None,
    ):
        # Existing Blockchain requires a valid 43-character
        # NEX-prefixed genesis validator.
        self.blockchain = (
            blockchain
            if blockchain is not None
            else Blockchain(
                genesis_validator=GENESIS_VALIDATOR
            )
        )

        self.consensus = (
            consensus
            if consensus is not None
            else ConsensusEngine()
        )

        self.committed_blocks = 0
        self.rejected_blocks = 0

    # ========================================================
    # VALIDATOR MANAGEMENT
    # ========================================================

    def register_validator(
        self,
        address: str,
        stake: int,
    ) -> Validator:

        return self.consensus.register_validator(
            address,
            stake,
        )

    # ========================================================
    # CONSENSUS SEED
    # ========================================================

    def consensus_seed(
        self,
        height: Optional[int] = None,
    ) -> str:
        """
        Generates a deterministic consensus seed from
        the next block height and current chain tip.
        """

        if height is None:
            height = self.blockchain.height + 1

        previous_hash = (
            self.blockchain.latest_block.block_hash
        )

        payload = (
            "NEXCHAIN-CONSENSUS:"
            f"{height}:"
            f"{previous_hash}"
        )

        return hashlib.sha256(
            payload.encode("utf-8")
        ).hexdigest()

    # ========================================================
    # PROPOSER SELECTION
    # ========================================================

    def select_proposer(
        self,
        height: Optional[int] = None,
    ) -> Validator:

        seed = self.consensus_seed(height)

        return self.consensus.select_validator(
            seed
        )

    # ========================================================
    # CANDIDATE BLOCK CREATION
    # ========================================================

    def create_candidate_block(
        self,
        validator_address: str,
        transactions: Optional[List] = None,
    ) -> Block:
        """
        Creates a candidate block only if the supplied
        validator is the deterministic proposer.
        """

        if transactions is None:
            transactions = []

        height = self.blockchain.height + 1

        seed = self.consensus_seed(height)

        if not self.consensus.validate_proposer(
            validator_address,
            seed,
        ):
            raise PermissionError(
                "Validator is not the selected proposer "
                f"for block height {height}."
            )

        validator = self.consensus.get_validator(
            validator_address
        )

        block = self.blockchain.create_next_block(
            validator=validator.address,
            transactions=transactions,
        )

        return block

    # ========================================================
    # CANDIDATE VALIDATION
    # ========================================================

    def validate_candidate(
        self,
        block: Block,
    ) -> Tuple[bool, str]:
        """
        Performs consensus-level and blockchain-level
        validation.
        """

        expected_height = (
            self.blockchain.height + 1
        )

        if block.height != expected_height:
            return (
                False,
                "Invalid block height.",
            )

        if (
            block.previous_hash
            != self.blockchain.latest_block.block_hash
        ):
            return (
                False,
                "Invalid previous block hash.",
            )

        if not block.validator:
            return (
                False,
                "Block validator is missing.",
            )

        validator = self.consensus.validators.get(
            block.validator
        )

        if validator is None:
            return (
                False,
                "Unknown block validator.",
            )

        if not validator.active:
            return (
                False,
                "Validator is inactive.",
            )

        seed = self.consensus_seed(
            block.height
        )

        selected = self.consensus.select_validator(
            seed
        )

        if selected.address != block.validator:
            return (
                False,
                "Validator is not the selected proposer.",
            )

        if not block.validate():
            return (
                False,
                "Block structural validation failed.",
            )

        return (
            True,
            "Block is valid.",
        )

    # ========================================================
    # BLOCK COMMITMENT
    # ========================================================

    def commit_block(
        self,
        block: Block,
    ) -> bool:
        """
        Validates and commits a candidate block.
        """

        valid, reason = self.validate_candidate(
            block
        )

        if not valid:

            self.rejected_blocks += 1

            if (
                block.validator
                in self.consensus.validators
            ):
                self.consensus.record_block_failure(
                    block.validator
                )

            raise ValueError(
                f"Block rejected: {reason}"
            )

        self.blockchain.add_block(block)

        self.consensus.record_block_success(
            block.validator
        )

        self.committed_blocks += 1

        return True

    # ========================================================
    # PRODUCE NEXT BLOCK
    # ========================================================

    def produce_block(
        self,
        transactions: Optional[List] = None,
    ) -> Block:
        """
        Automatically:
        1. selects proposer
        2. creates candidate
        3. validates candidate
        4. commits candidate
        """

        proposer = self.select_proposer()

        block = self.create_candidate_block(
            proposer.address,
            transactions,
        )

        self.commit_block(block)

        return block

    # ========================================================
    # CHAIN VALIDATION
    # ========================================================

    def validate_chain(self) -> bool:

        return self.blockchain.validate_chain()

    # ========================================================
    # STATISTICS
    # ========================================================

    def stats(self) -> dict:

        blockchain_stats = (
            self.blockchain.stats()
        )

        consensus_stats = (
            self.consensus.stats()
        )

        return {
            "blockchain": blockchain_stats,
            "consensus": consensus_stats,
            "committed_blocks": self.committed_blocks,
            "rejected_blocks": self.rejected_blocks,
        }

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict:

        return {
            "blockchain": self.blockchain.to_dict(),
            "consensus": self.consensus.to_dict(),
            "committed_blocks": self.committed_blocks,
            "rejected_blocks": self.rejected_blocks,
        }

    def to_json(self) -> str:

        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            indent=2,
        )


# ============================================================
# SELF TEST
# ============================================================

def self_test():

    print("=" * 70)
    print("NEXCHAIN CONSENSUS-BLOCKCHAIN INTEGRATION TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # Create integrated system
    # --------------------------------------------------------

    system = ConsensusBlockchain()

    print("[PASS] Blockchain + consensus initialization")

    # --------------------------------------------------------
    # Register validators
    # --------------------------------------------------------

    system.register_validator(
        "NEX" + ("1" * 40),
        10_000,
    )

    system.register_validator(
        "NEX" + ("2" * 40),
        25_000,
    )

    system.register_validator(
        "NEX" + ("3" * 40),
        50_000,
    )

    print("[PASS] Validators registered")

    # --------------------------------------------------------
    # Verify validator addresses
    # --------------------------------------------------------

    for validator in system.consensus.validators.values():

        assert len(validator.address) == 43
        assert validator.address.startswith("NEX")

    print("[PASS] Validator address format")

    # --------------------------------------------------------
    # Select proposer
    # --------------------------------------------------------

    proposer = system.select_proposer()

    assert (
        proposer.address
        in system.consensus.validators
    )

    print(
        "[PASS] Proposer selected:",
        proposer.address,
    )

    # --------------------------------------------------------
    # Produce first block
    # --------------------------------------------------------

    block = system.produce_block()

    assert block.height == 1

    assert (
        block.validator
        == proposer.address
    )

    print("[PASS] First block produced")

    # --------------------------------------------------------
    # Validate chain
    # --------------------------------------------------------

    assert system.validate_chain()

    print("[PASS] Chain validation")

    # --------------------------------------------------------
    # Produce additional blocks
    # --------------------------------------------------------

    for _ in range(4):

        block = system.produce_block()

        assert (
            block.height
            == system.blockchain.height
        )

    print("[PASS] Multi-block production")

    # --------------------------------------------------------
    # Verify height
    # --------------------------------------------------------

    assert system.blockchain.height == 5

    print("[PASS] Chain height progression")

    # --------------------------------------------------------
    # Verify consensus participation
    # --------------------------------------------------------

    total_successes = sum(
        validator.successful_blocks
        for validator
        in system.consensus.validators.values()
    )

    assert total_successes == 5

    print(
        "[PASS] Consensus participation tracking"
    )

    # --------------------------------------------------------
    # Test unauthorized proposer
    # --------------------------------------------------------

    current_proposer = (
        system.select_proposer()
    )

    wrong_validator = next(
        validator
        for validator
        in system.consensus.validators.values()
        if validator.address
        != current_proposer.address
    )

    try:

        system.create_candidate_block(
            wrong_validator.address
        )

        raise AssertionError(
            "Unauthorized proposer was accepted."
        )

    except PermissionError:

        pass

    print(
        "[PASS] Unauthorized proposer rejection"
    )

    # --------------------------------------------------------
    # Final chain validation
    # --------------------------------------------------------

    assert system.validate_chain()

    print(
        "[PASS] Final blockchain validation"
    )

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    print()
    print("SYSTEM STATISTICS")
    print("-" * 70)

    print(
        json.dumps(
            system.stats(),
            indent=2,
        )
    )

    print()
    print("=" * 70)
    print(
        "ALL CONSENSUS-BLOCKCHAIN TESTS PASSED"
    )
    print("=" * 70)


if __name__ == "__main__":
    self_test()