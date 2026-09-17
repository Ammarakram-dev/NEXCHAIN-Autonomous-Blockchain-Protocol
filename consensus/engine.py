"""
NEXCHAIN Consensus Engine
=========================

Custom validator selection foundation for NEXCHAIN.

Validator score combines:
- Stake
- Reputation
- Successful validations
- Participation
- Penalties
- Deterministic block randomness

This is intentionally designed as a modular consensus layer so the
network, state machine, and slashing mechanisms can evolve independently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import hashlib
import json
import time


@dataclass
class Validator:
    """
    Represents a NEXCHAIN validator.
    """

    address: str
    stake: int
    reputation: float = 1.0

    successful_blocks: int = 0
    failed_blocks: int = 0
    participated_blocks: int = 0
    missed_blocks: int = 0

    total_rewards: int = 0
    total_penalties: int = 0

    active: bool = True
    joined_at: float = field(default_factory=time.time)

    def success_rate(self) -> float:
        total = self.successful_blocks + self.failed_blocks

        if total == 0:
            return 1.0

        return self.successful_blocks / total

    def participation_rate(self) -> float:
        total = self.participated_blocks + self.missed_blocks

        if total == 0:
            return 1.0

        return self.participated_blocks / total

    def effective_reputation(self) -> float:
        """
        Calculates a bounded reputation value.

        Reputation is influenced by:
        - base reputation
        - historical success
        - network participation
        """

        success = self.success_rate()
        participation = self.participation_rate()

        score = (
            self.reputation * 0.50
            + success * 0.30
            + participation * 0.20
        )

        return max(0.0, min(score, 1.0))

    def validator_score(self) -> float:
        """
        Final validator weight.

        Stake provides economic weight while reputation and
        participation protect the network from purely capital-based
        validator selection.
        """

        if not self.active or self.stake <= 0:
            return 0.0

        reputation = self.effective_reputation()

        stake_factor = self.stake ** 0.5

        return stake_factor * reputation

    def record_success(self, reward: int = 0) -> None:
        self.successful_blocks += 1
        self.participated_blocks += 1

        self.reputation = min(
            1.0,
            self.reputation + 0.01
        )

        self.total_rewards += reward

    def record_failure(self, penalty: int = 0) -> None:
        self.failed_blocks += 1
        self.participated_blocks += 1

        self.reputation = max(
            0.0,
            self.reputation - 0.05
        )

        self.total_penalties += penalty

    def record_missed_block(self) -> None:
        self.missed_blocks += 1

        self.reputation = max(
            0.0,
            self.reputation - 0.01
        )

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "stake": self.stake,
            "reputation": self.reputation,
            "successful_blocks": self.successful_blocks,
            "failed_blocks": self.failed_blocks,
            "participated_blocks": self.participated_blocks,
            "missed_blocks": self.missed_blocks,
            "total_rewards": self.total_rewards,
            "total_penalties": self.total_penalties,
            "active": self.active,
            "joined_at": self.joined_at,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Validator":
        return cls(
            address=data["address"],
            stake=int(data["stake"]),
            reputation=float(data.get("reputation", 1.0)),
            successful_blocks=int(data.get("successful_blocks", 0)),
            failed_blocks=int(data.get("failed_blocks", 0)),
            participated_blocks=int(data.get("participated_blocks", 0)),
            missed_blocks=int(data.get("missed_blocks", 0)),
            total_rewards=int(data.get("total_rewards", 0)),
            total_penalties=int(data.get("total_penalties", 0)),
            active=bool(data.get("active", True)),
            joined_at=float(data.get("joined_at", time.time())),
        )


class ConsensusEngine:
    """
    NEXCHAIN custom consensus engine.

    Responsibilities:
    - validator registration
    - validator activation/deactivation
    - validator scoring
    - deterministic validator selection
    - block participation tracking
    - validator rewards and penalties
    """

    MINIMUM_STAKE = 1_000
    MAX_VALIDATORS = 10_000

    REWARD_PER_BLOCK = 10
    MISSED_BLOCK_PENALTY = 1
    INVALID_BLOCK_PENALTY = 25

    def __init__(self):
        self.validators: Dict[str, Validator] = {}
        self.total_blocks = 0

    # ---------------------------------------------------------
    # Validator management
    # ---------------------------------------------------------

    def register_validator(
        self,
        address: str,
        stake: int,
    ) -> Validator:

        if not address:
            raise ValueError("Validator address cannot be empty.")

        if address in self.validators:
            raise ValueError("Validator already registered.")

        if stake < self.MINIMUM_STAKE:
            raise ValueError(
                f"Minimum validator stake is "
                f"{self.MINIMUM_STAKE} NEX."
            )

        if len(self.validators) >= self.MAX_VALIDATORS:
            raise ValueError("Maximum validator count reached.")

        validator = Validator(
            address=address,
            stake=stake,
        )

        self.validators[address] = validator

        return validator

    def remove_validator(self, address: str) -> None:

        validator = self.get_validator(address)

        validator.active = False

    def activate_validator(self, address: str) -> None:

        validator = self.get_validator(address)

        if validator.stake < self.MINIMUM_STAKE:
            raise ValueError(
                "Validator does not meet minimum stake."
            )

        validator.active = True

    def get_validator(self, address: str) -> Validator:

        validator = self.validators.get(address)

        if validator is None:
            raise ValueError(
                f"Unknown validator: {address}"
            )

        return validator

    # ---------------------------------------------------------
    # Validator scoring
    # ---------------------------------------------------------

    def get_active_validators(self) -> List[Validator]:

        return [
            validator
            for validator in self.validators.values()
            if validator.active
            and validator.stake >= self.MINIMUM_STAKE
        ]

    def validator_scores(self) -> Dict[str, float]:

        return {
            validator.address: validator.validator_score()
            for validator in self.get_active_validators()
        }

    # ---------------------------------------------------------
    # Deterministic selection
    # ---------------------------------------------------------

    @staticmethod
    def _selection_hash(
        seed: str,
        address: str,
    ) -> int:

        value = hashlib.sha256(
            f"{seed}:{address}".encode("utf-8")
        ).hexdigest()

        return int(value, 16)

    def select_validator(
        self,
        seed: str,
    ) -> Validator:

        candidates = self.get_active_validators()

        if not candidates:
            raise RuntimeError(
                "No active validators available."
            )

        scored = []

        for validator in candidates:

            score = validator.validator_score()

            if score <= 0:
                continue

            randomness = self._selection_hash(
                seed,
                validator.address,
            )

            # Convert deterministic hash into [0,1).
            random_factor = randomness / ((1 << 256) - 1)

            # Higher validator score improves selection probability.
            selection_value = random_factor ** (1.0 / score)

            scored.append(
                (
                    selection_value,
                    validator,
                )
            )

        if not scored:
            raise RuntimeError(
                "No eligible validators available."
            )

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return scored[0][1]

    def select_validators(
        self,
        seed: str,
        count: int,
    ) -> List[Validator]:

        if count <= 0:
            raise ValueError(
                "Validator count must be positive."
            )

        candidates = self.get_active_validators()

        if count > len(candidates):
            count = len(candidates)

        scored = []

        for validator in candidates:

            score = validator.validator_score()

            if score <= 0:
                continue

            randomness = self._selection_hash(
                seed,
                validator.address,
            )

            random_factor = randomness / ((1 << 256) - 1)

            selection_value = random_factor ** (1.0 / score)

            scored.append(
                (
                    selection_value,
                    validator,
                )
            )

        scored.sort(
            key=lambda item: item[0],
            reverse=True,
        )

        return [
            validator
            for _, validator in scored[:count]
        ]

    # ---------------------------------------------------------
    # Block lifecycle
    # ---------------------------------------------------------

    def begin_block(self) -> None:
        self.total_blocks += 1

        for validator in self.get_active_validators():
            validator.participated_blocks = max(
                validator.participated_blocks,
                0,
            )

    def record_block_success(
        self,
        validator_address: str,
    ) -> None:

        validator = self.get_validator(
            validator_address
        )

        validator.record_success(
            reward=self.REWARD_PER_BLOCK
        )

    def record_block_failure(
        self,
        validator_address: str,
    ) -> None:

        validator = self.get_validator(
            validator_address
        )

        validator.record_failure(
            penalty=self.INVALID_BLOCK_PENALTY
        )

    def record_missed_block(
        self,
        validator_address: str,
    ) -> None:

        validator = self.get_validator(
            validator_address
        )

        validator.record_missed_block()

    # ---------------------------------------------------------
    # Consensus decision
    # ---------------------------------------------------------

    def validate_proposer(
        self,
        validator_address: str,
        seed: str,
    ) -> bool:

        selected = self.select_validator(seed)

        return selected.address == validator_address

    # ---------------------------------------------------------
    # Persistence
    # ---------------------------------------------------------

    def to_dict(self) -> dict:

        return {
            "total_blocks": self.total_blocks,
            "validators": {
                address: validator.to_dict()
                for address, validator
                in self.validators.items()
            },
        }

    def to_json(self) -> str:

        return json.dumps(
            self.to_dict(),
            sort_keys=True,
            indent=2,
        )

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "ConsensusEngine":

        engine = cls()

        engine.total_blocks = int(
            data.get("total_blocks", 0)
        )

        validators = data.get(
            "validators",
            {},
        )

        for address, validator_data in validators.items():

            engine.validators[address] = (
                Validator.from_dict(
                    validator_data
                )
            )

        return engine

    # ---------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------

    def stats(self) -> dict:

        active = self.get_active_validators()

        total_stake = sum(
            validator.stake
            for validator in active
        )

        return {
            "total_validators": len(self.validators),
            "active_validators": len(active),
            "total_stake": total_stake,
            "total_blocks": self.total_blocks,
        }


def self_test():

    print("=" * 70)
    print("NEXCHAIN CONSENSUS ENGINE SELF-TEST")
    print("=" * 70)

    engine = ConsensusEngine()

    # ---------------------------------------------------------
    # Test validator registration
    # ---------------------------------------------------------

    v1 = engine.register_validator(
        "NEXValidatorA",
        10_000,
    )

    v2 = engine.register_validator(
        "NEXValidatorB",
        25_000,
    )

    v3 = engine.register_validator(
        "NEXValidatorC",
        50_000,
    )

    assert len(engine.validators) == 3

    print("[PASS] Validator registration")

    # ---------------------------------------------------------
    # Test minimum stake
    # ---------------------------------------------------------

    try:

        engine.register_validator(
            "InvalidValidator",
            100,
        )

        raise AssertionError(
            "Low-stake validator was accepted."
        )

    except ValueError:

        pass

    print("[PASS] Minimum stake enforcement")

    # ---------------------------------------------------------
    # Test scoring
    # ---------------------------------------------------------

    scores = engine.validator_scores()

    assert len(scores) == 3

    for score in scores.values():
        assert score > 0

    print("[PASS] Validator scoring")

    # ---------------------------------------------------------
    # Test deterministic selection
    # ---------------------------------------------------------

    selected_1 = engine.select_validator(
        "test-seed-001"
    )

    selected_2 = engine.select_validator(
        "test-seed-001"
    )

    assert selected_1.address == selected_2.address

    print("[PASS] Deterministic validator selection")

    # ---------------------------------------------------------
    # Test multi-validator selection
    # ---------------------------------------------------------

    selected = engine.select_validators(
        "test-seed-002",
        2,
    )

    assert len(selected) == 2

    assert len(
        set(v.address for v in selected)
    ) == 2

    print("[PASS] Multi-validator selection")

    # ---------------------------------------------------------
    # Test successful block
    # ---------------------------------------------------------

    engine.record_block_success(
        selected_1.address
    )

    validator = engine.get_validator(
        selected_1.address
    )

    assert validator.successful_blocks == 1
    assert validator.total_rewards == 10

    print("[PASS] Successful block recording")

    # ---------------------------------------------------------
    # Test failed block
    # ---------------------------------------------------------

    engine.record_block_failure(
        selected_1.address
    )

    assert validator.failed_blocks == 1
    assert validator.total_penalties == 25

    print("[PASS] Failed block recording")

    # ---------------------------------------------------------
    # Test missed block
    # ---------------------------------------------------------

    old_reputation = validator.reputation

    engine.record_missed_block(
        selected_1.address
    )

    assert validator.reputation < old_reputation

    print("[PASS] Missed block penalty")

    # ---------------------------------------------------------
    # Test proposer validation
    # ---------------------------------------------------------

    seed = "proposal-seed"

    proposer = engine.select_validator(seed)

    assert engine.validate_proposer(
        proposer.address,
        seed,
    )

    print("[PASS] Proposer validation")

    # ---------------------------------------------------------
    # Test deactivation
    # ---------------------------------------------------------

    engine.remove_validator(
        v1.address
    )

    assert not engine.get_validator(
        v1.address
    ).active

    assert v1.address not in engine.validator_scores()

    print("[PASS] Validator deactivation")

    # ---------------------------------------------------------
    # Test serialization
    # ---------------------------------------------------------

    serialized = engine.to_json()

    restored = ConsensusEngine.from_dict(
        json.loads(serialized)
    )

    assert len(restored.validators) == 3

    assert (
        restored.total_blocks
        == engine.total_blocks
    )

    print("[PASS] Consensus state serialization")

    # ---------------------------------------------------------
    # Statistics
    # ---------------------------------------------------------

    stats = engine.stats()

    print()
    print("Consensus statistics:")
    print(json.dumps(stats, indent=2))

    print()
    print("=" * 70)
    print("ALL CONSENSUS TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()