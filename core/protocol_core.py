"""
NEXCHAIN — Protocol Core
STEP 20 — Final Core Integrity Layer

Purpose
-------
Final protocol-grade core layer for NEXCHAIN.

This module is intentionally self-contained:
- no HTTP
- no RPC
- no frontend
- no database dependency
- no external services
- no third-party integrations

It provides:
- protocol identity
- deterministic protocol metadata
- finality checkpoints
- state-root checkpoints
- validator observations
- transaction replay protection
- supply invariants
- contract-state tracking
- audit records
- integrity sealing
- snapshot / restore
- health reporting
- deterministic serialization
- complete self-test

Python:
    3.12+

NEXCHAIN:
    Native token: NEX
"""

from __future__ import annotations

import hashlib
import json
import time
from copy import deepcopy
from dataclasses import dataclass, field
from typing import Any, Iterable


# ============================================================================
# PROTOCOL CONSTANTS
# ============================================================================

PROTOCOL_NAME = "NEXCHAIN"
PROTOCOL_VERSION = 1
PROTOCOL_NAME_VERSION = f"{PROTOCOL_NAME}/{PROTOCOL_VERSION}"

NATIVE_ASSET = "NEX"

MAX_SUPPLY = 21_000_000_000.0

GENESIS_HEIGHT = 0
GENESIS_HASH = "0" * 64

MAX_AUDIT_RECORDS = 100_000
MAX_FINALITY_DEPTH = 100_000
MAX_CHECKPOINTS = 100_000
MAX_VALIDATORS = 10_000

HASH_SIZE = 64


# ============================================================================
# ERRORS
# ============================================================================

class ProtocolCoreError(Exception):
    """Base protocol-core exception."""


class ProtocolValidationError(ProtocolCoreError):
    """Raised when protocol data violates an invariant."""


class IntegrityError(ProtocolCoreError):
    """Raised when integrity verification fails."""


class SnapshotError(ProtocolCoreError):
    """Raised when snapshot restoration fails."""


# ============================================================================
# DETERMINISTIC HELPERS
# ============================================================================

def canonical_json(value: Any) -> str:
    """
    Produce deterministic JSON.

    The protocol never relies on dictionary insertion order when hashing
    important state.
    """
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def sha256_hex(data: bytes | str) -> str:
    if isinstance(data, str):
        data = data.encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def hash_object(value: Any) -> str:
    return sha256_hex(canonical_json(value))


def valid_hash(value: str) -> bool:
    if not isinstance(value, str):
        return False

    if len(value) != HASH_SIZE:
        return False

    try:
        int(value, 16)
    except ValueError:
        return False

    return True


def valid_address(value: str) -> bool:
    """
    NEXCHAIN addresses are 43 characters:
        NEX + 40 hexadecimal characters
    """
    if not isinstance(value, str):
        return False

    if len(value) != 43:
        return False

    if not value.startswith("NEX"):
        return False

    try:
        int(value[3:], 16)
    except ValueError:
        return False

    return True


# ============================================================================
# PROTOCOL IDENTITY
# ============================================================================

@dataclass(frozen=True)
class ProtocolIdentity:
    name: str = PROTOCOL_NAME
    version: int = PROTOCOL_VERSION
    native_asset: str = NATIVE_ASSET
    max_supply: float = MAX_SUPPLY

    def __post_init__(self) -> None:
        if self.name != PROTOCOL_NAME:
            raise ProtocolValidationError("Invalid protocol name.")

        if self.version != PROTOCOL_VERSION:
            raise ProtocolValidationError("Invalid protocol version.")

        if self.native_asset != NATIVE_ASSET:
            raise ProtocolValidationError("Invalid native asset.")

        if self.max_supply <= 0:
            raise ProtocolValidationError("Invalid maximum supply.")

    @property
    def identifier(self) -> str:
        return f"{self.name}:{self.version}:{self.native_asset}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "native_asset": self.native_asset,
            "max_supply": self.max_supply,
            "identifier": self.identifier,
        }


# ============================================================================
# BLOCK FINALITY
# ============================================================================

@dataclass(frozen=True)
class FinalityCheckpoint:
    height: int
    block_hash: str
    state_root: str
    validator_set_hash: str
    timestamp: float

    def __post_init__(self) -> None:
        if self.height < GENESIS_HEIGHT:
            raise ProtocolValidationError("Invalid finality height.")

        if not valid_hash(self.block_hash):
            raise ProtocolValidationError("Invalid finality block hash.")

        if not valid_hash(self.state_root):
            raise ProtocolValidationError("Invalid finality state root.")

        if not valid_hash(self.validator_set_hash):
            raise ProtocolValidationError(
                "Invalid validator-set hash."
            )

        if self.timestamp <= 0:
            raise ProtocolValidationError("Invalid finality timestamp.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "height": self.height,
            "block_hash": self.block_hash,
            "state_root": self.state_root,
            "validator_set_hash": self.validator_set_hash,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FinalityCheckpoint":
        return cls(
            height=int(data["height"]),
            block_hash=str(data["block_hash"]),
            state_root=str(data["state_root"]),
            validator_set_hash=str(data["validator_set_hash"]),
            timestamp=float(data["timestamp"]),
        )


# ============================================================================
# STATE CHECKPOINT
# ============================================================================

@dataclass(frozen=True)
class StateCheckpoint:
    height: int
    block_hash: str
    state_root: str
    total_supply: float
    account_count: int
    contract_count: int
    timestamp: float

    def __post_init__(self) -> None:
        if self.height < 0:
            raise ProtocolValidationError("Invalid state height.")

        if not valid_hash(self.block_hash):
            raise ProtocolValidationError("Invalid state block hash.")

        if not valid_hash(self.state_root):
            raise ProtocolValidationError("Invalid state root.")

        if self.total_supply < 0:
            raise ProtocolValidationError("Negative total supply.")

        if self.total_supply > MAX_SUPPLY:
            raise ProtocolValidationError("Maximum supply exceeded.")

        if self.account_count < 0:
            raise ProtocolValidationError("Invalid account count.")

        if self.contract_count < 0:
            raise ProtocolValidationError("Invalid contract count.")

        if self.timestamp <= 0:
            raise ProtocolValidationError("Invalid state timestamp.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "height": self.height,
            "block_hash": self.block_hash,
            "state_root": self.state_root,
            "total_supply": self.total_supply,
            "account_count": self.account_count,
            "contract_count": self.contract_count,
            "timestamp": self.timestamp,
        }


# ============================================================================
# VALIDATOR OBSERVATION
# ============================================================================

@dataclass
class ValidatorObservation:
    address: str
    blocks_proposed: int = 0
    blocks_finalized: int = 0
    invalid_blocks: int = 0
    missed_blocks: int = 0
    active: bool = True

    def __post_init__(self) -> None:
        if not valid_address(self.address):
            raise ProtocolValidationError(
                f"Invalid validator address: {self.address}"
            )

        for value in (
            self.blocks_proposed,
            self.blocks_finalized,
            self.invalid_blocks,
            self.missed_blocks,
        ):
            if value < 0:
                raise ProtocolValidationError(
                    "Validator counters cannot be negative."
                )

    @property
    def success_rate(self) -> float:
        total = self.blocks_proposed + self.invalid_blocks

        if total == 0:
            return 1.0

        return self.blocks_proposed / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "blocks_proposed": self.blocks_proposed,
            "blocks_finalized": self.blocks_finalized,
            "invalid_blocks": self.invalid_blocks,
            "missed_blocks": self.missed_blocks,
            "active": self.active,
            "success_rate": self.success_rate,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValidatorObservation":
        return cls(
            address=str(data["address"]),
            blocks_proposed=int(data["blocks_proposed"]),
            blocks_finalized=int(data["blocks_finalized"]),
            invalid_blocks=int(data["invalid_blocks"]),
            missed_blocks=int(data["missed_blocks"]),
            active=bool(data["active"]),
        )


# ============================================================================
# AUDIT RECORD
# ============================================================================

@dataclass(frozen=True)
class AuditRecord:
    sequence: int
    event: str
    height: int
    payload_hash: str
    previous_record_hash: str
    record_hash: str
    timestamp: float

    @staticmethod
    def calculate_hash(
        sequence: int,
        event: str,
        height: int,
        payload_hash: str,
        previous_record_hash: str,
        timestamp: float,
    ) -> str:
        payload = {
            "sequence": sequence,
            "event": event,
            "height": height,
            "payload_hash": payload_hash,
            "previous_record_hash": previous_record_hash,
            "timestamp": timestamp,
        }

        return hash_object(payload)

    @classmethod
    def create(
        cls,
        sequence: int,
        event: str,
        height: int,
        payload: Any,
        previous_record_hash: str,
        timestamp: float | None = None,
    ) -> "AuditRecord":
        if not event:
            raise ProtocolValidationError("Audit event cannot be empty.")

        if height < 0:
            raise ProtocolValidationError("Invalid audit height.")

        if not valid_hash(previous_record_hash):
            raise ProtocolValidationError(
                "Invalid previous audit hash."
            )

        timestamp = time.time() if timestamp is None else float(timestamp)

        payload_hash = hash_object(payload)

        record_hash = cls.calculate_hash(
            sequence=sequence,
            event=event,
            height=height,
            payload_hash=payload_hash,
            previous_record_hash=previous_record_hash,
            timestamp=timestamp,
        )

        return cls(
            sequence=sequence,
            event=event,
            height=height,
            payload_hash=payload_hash,
            previous_record_hash=previous_record_hash,
            record_hash=record_hash,
            timestamp=timestamp,
        )

    def verify(self) -> bool:
        expected = self.calculate_hash(
            sequence=self.sequence,
            event=self.event,
            height=self.height,
            payload_hash=self.payload_hash,
            previous_record_hash=self.previous_record_hash,
            timestamp=self.timestamp,
        )

        return expected == self.record_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "event": self.event,
            "height": self.height,
            "payload_hash": self.payload_hash,
            "previous_record_hash": self.previous_record_hash,
            "record_hash": self.record_hash,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AuditRecord":
        record = cls(
            sequence=int(data["sequence"]),
            event=str(data["event"]),
            height=int(data["height"]),
            payload_hash=str(data["payload_hash"]),
            previous_record_hash=str(data["previous_record_hash"]),
            record_hash=str(data["record_hash"]),
            timestamp=float(data["timestamp"]),
        )

        if not record.verify():
            raise IntegrityError("Invalid audit record.")

        return record


# ============================================================================
# CORE SNAPSHOT
# ============================================================================

@dataclass
class ProtocolCoreSnapshot:
    height: int
    latest_block_hash: str
    latest_state_root: str
    total_supply: float
    finality: list[dict[str, Any]]
    state_checkpoints: list[dict[str, Any]]
    validators: dict[str, dict[str, Any]]
    transaction_index: list[str]
    contract_index: list[str]
    audit_records: list[dict[str, Any]]
    protocol_seal: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "height": self.height,
            "latest_block_hash": self.latest_block_hash,
            "latest_state_root": self.latest_state_root,
            "total_supply": self.total_supply,
            "finality": deepcopy(self.finality),
            "state_checkpoints": deepcopy(self.state_checkpoints),
            "validators": deepcopy(self.validators),
            "transaction_index": list(self.transaction_index),
            "contract_index": list(self.contract_index),
            "audit_records": deepcopy(self.audit_records),
            "protocol_seal": self.protocol_seal,
        }


# ============================================================================
# PROTOCOL CORE
# ============================================================================

class ProtocolCore:
    """
    Final NEXCHAIN protocol-core integrity layer.

    This object does not own networking, databases, RPC, wallets,
    mempool execution, or contract VM execution.

    It records and verifies the results produced by those layers.
    """

    def __init__(
        self,
        *,
        genesis_block_hash: str = GENESIS_HASH,
        genesis_state_root: str | None = None,
    ) -> None:
        if not valid_hash(genesis_block_hash):
            raise ProtocolValidationError(
                "Genesis block hash must be a 64-character hexadecimal hash."
            )

        if genesis_state_root is None:
            genesis_state_root = hash_object(
                {
                    "protocol": PROTOCOL_NAME_VERSION,
                    "genesis": True,
                }
            )

        if not valid_hash(genesis_state_root):
            raise ProtocolValidationError(
                "Invalid genesis state root."
            )

        self.identity = ProtocolIdentity()

        self.height = GENESIS_HEIGHT
        self.latest_block_hash = genesis_block_hash
        self.latest_state_root = genesis_state_root
        self.total_supply = 0.0

        self.finality: list[FinalityCheckpoint] = []
        self.state_checkpoints: list[StateCheckpoint] = []

        self.validators: dict[str, ValidatorObservation] = {}

        self.transaction_index: set[str] = set()
        self.contract_index: set[str] = set()

        self.audit_records: list[AuditRecord] = []

        self._append_audit(
            event="GENESIS_INITIALIZED",
            height=0,
            payload={
                "protocol": self.identity.to_dict(),
                "genesis_block_hash": genesis_block_hash,
                "genesis_state_root": genesis_state_root,
            },
            timestamp=1700000000.0,
        )

        self._seal = self._calculate_seal()

    # ------------------------------------------------------------------
    # BASIC PROPERTIES
    # ------------------------------------------------------------------

    @property
    def protocol_id(self) -> str:
        return self.identity.identifier

    @property
    def finalized_height(self) -> int:
        if not self.finality:
            return 0

        return self.finality[-1].height

    @property
    def validator_count(self) -> int:
        return len(self.validators)

    @property
    def transaction_count(self) -> int:
        return len(self.transaction_index)

    @property
    def contract_count(self) -> int:
        return len(self.contract_index)

    @property
    def audit_root(self) -> str:
        if not self.audit_records:
            return sha256_hex(b"")

        return self.audit_records[-1].record_hash

    # ------------------------------------------------------------------
    # INTERNAL AUDIT
    # ------------------------------------------------------------------

    def _append_audit(
        self,
        *,
        event: str,
        height: int,
        payload: Any,
        timestamp: float | None = None,
    ) -> AuditRecord:
        if len(self.audit_records) >= MAX_AUDIT_RECORDS:
            raise ProtocolCoreError(
                "Audit record capacity exceeded."
            )

        previous_hash = (
            self.audit_records[-1].record_hash
            if self.audit_records
            else sha256_hex(b"GENESIS-AUDIT")
        )

        record = AuditRecord.create(
            sequence=len(self.audit_records),
            event=event,
            height=height,
            payload=payload,
            previous_record_hash=previous_hash,
            timestamp=timestamp,
        )

        self.audit_records.append(record)

        return record

    # ------------------------------------------------------------------
    # VALIDATOR MANAGEMENT
    # ------------------------------------------------------------------

    def register_validator(self, address: str) -> None:
        if not valid_address(address):
            raise ProtocolValidationError(
                "Invalid validator address."
            )

        if address in self.validators:
            return

        if len(self.validators) >= MAX_VALIDATORS:
            raise ProtocolCoreError(
                "Maximum validator count reached."
            )

        self.validators[address] = ValidatorObservation(
            address=address
        )

        self._append_audit(
            event="VALIDATOR_REGISTERED",
            height=self.height,
            payload={"address": address},
        )

        self._refresh_seal()

    def record_block_proposed(self, validator: str) -> None:
        self._require_validator(validator)

        observation = self.validators[validator]
        observation.blocks_proposed += 1

        self._append_audit(
            event="BLOCK_PROPOSED",
            height=self.height,
            payload={
                "validator": validator,
                "blocks_proposed": observation.blocks_proposed,
            },
        )

        self._refresh_seal()

    def record_block_finalized(self, validator: str) -> None:
        self._require_validator(validator)

        observation = self.validators[validator]
        observation.blocks_finalized += 1

        self._append_audit(
            event="BLOCK_FINALIZED_BY_VALIDATOR",
            height=self.height,
            payload={
                "validator": validator,
                "blocks_finalized": observation.blocks_finalized,
            },
        )

        self._refresh_seal()

    def record_invalid_block(self, validator: str) -> None:
        self._require_validator(validator)

        observation = self.validators[validator]
        observation.invalid_blocks += 1

        self._append_audit(
            event="INVALID_BLOCK_RECORDED",
            height=self.height,
            payload={
                "validator": validator,
                "invalid_blocks": observation.invalid_blocks,
            },
        )

        self._refresh_seal()

    def record_missed_block(self, validator: str) -> None:
        self._require_validator(validator)

        observation = self.validators[validator]
        observation.missed_blocks += 1

        self._append_audit(
            event="MISSED_BLOCK_RECORDED",
            height=self.height,
            payload={
                "validator": validator,
                "missed_blocks": observation.missed_blocks,
            },
        )

        self._refresh_seal()

    def _require_validator(self, address: str) -> None:
        if address not in self.validators:
            raise ProtocolValidationError(
                "Validator is not registered."
            )

    # ------------------------------------------------------------------
    # TRANSACTION REPLAY PROTECTION
    # ------------------------------------------------------------------

    def register_transaction(self, transaction_hash: str) -> bool:
        if not valid_hash(transaction_hash):
            raise ProtocolValidationError(
                "Invalid transaction hash."
            )

        if transaction_hash in self.transaction_index:
            return False

        self.transaction_index.add(transaction_hash)

        self._append_audit(
            event="TRANSACTION_REGISTERED",
            height=self.height,
            payload={
                "transaction_hash": transaction_hash,
            },
        )

        self._refresh_seal()

        return True

    def has_transaction(self, transaction_hash: str) -> bool:
        return transaction_hash in self.transaction_index

    # ------------------------------------------------------------------
    # CONTRACT REGISTRY
    # ------------------------------------------------------------------

    def register_contract(self, contract_address: str) -> bool:
        if not isinstance(contract_address, str):
            raise ProtocolValidationError(
                "Contract address must be a string."
            )

        if len(contract_address) != 43:
            raise ProtocolValidationError(
                "Invalid contract address length."
            )

        if not contract_address.startswith("C"):
            raise ProtocolValidationError(
                "Invalid contract address prefix."
            )

        try:
            int(contract_address[1:], 16)
        except ValueError as exc:
            raise ProtocolValidationError(
                "Invalid contract address encoding."
            ) from exc

        if contract_address in self.contract_index:
            return False

        self.contract_index.add(contract_address)

        self._append_audit(
            event="CONTRACT_REGISTERED",
            height=self.height,
            payload={
                "contract_address": contract_address,
            },
        )

        self._refresh_seal()

        return True

    def has_contract(self, contract_address: str) -> bool:
        return contract_address in self.contract_index

    # ------------------------------------------------------------------
    # STATE COMMITMENT
    # ------------------------------------------------------------------

    def commit_block(
        self,
        *,
        height: int,
        block_hash: str,
        state_root: str,
        total_supply: float,
        account_count: int,
        contract_count: int,
        validator_set_hash: str,
        timestamp: float | None = None,
    ) -> StateCheckpoint:
        """
        Record the result of a successfully validated block.

        This does not execute the block. Execution belongs to the
        specialized core engines from previous steps.
        """
        if height != self.height + 1:
            raise ProtocolValidationError(
                f"Invalid block height. Expected {self.height + 1}."
            )

        if not valid_hash(block_hash):
            raise ProtocolValidationError(
                "Invalid block hash."
            )

        if not valid_hash(state_root):
            raise ProtocolValidationError(
                "Invalid state root."
            )

        if not valid_hash(validator_set_hash):
            raise ProtocolValidationError(
                "Invalid validator-set hash."
            )

        if total_supply < 0:
            raise ProtocolValidationError(
                "Total supply cannot be negative."
            )

        if total_supply > MAX_SUPPLY:
            raise ProtocolValidationError(
                "Maximum supply exceeded."
            )

        if account_count < 0:
            raise ProtocolValidationError(
                "Invalid account count."
            )

        if contract_count < 0:
            raise ProtocolValidationError(
                "Invalid contract count."
            )

        timestamp = time.time() if timestamp is None else float(timestamp)

        if timestamp <= 0:
            raise ProtocolValidationError(
                "Invalid block timestamp."
            )

        self.height = height
        self.latest_block_hash = block_hash
        self.latest_state_root = state_root
        self.total_supply = float(total_supply)

        checkpoint = StateCheckpoint(
            height=height,
            block_hash=block_hash,
            state_root=state_root,
            total_supply=self.total_supply,
            account_count=account_count,
            contract_count=contract_count,
            timestamp=timestamp,
        )

        self.state_checkpoints.append(checkpoint)

        if len(self.state_checkpoints) > MAX_CHECKPOINTS:
            self.state_checkpoints.pop(0)

        self._append_audit(
            event="BLOCK_COMMITTED",
            height=height,
            payload={
                "block_hash": block_hash,
                "state_root": state_root,
                "total_supply": self.total_supply,
                "account_count": account_count,
                "contract_count": contract_count,
                "validator_set_hash": validator_set_hash,
            },
            timestamp=timestamp,
        )

        self._refresh_seal()

        return checkpoint

    # ------------------------------------------------------------------
    # FINALITY
    # ------------------------------------------------------------------

    def finalize_block(
        self,
        *,
        height: int,
        block_hash: str,
        state_root: str,
        validator_set_hash: str,
        timestamp: float | None = None,
    ) -> FinalityCheckpoint:
        if height > self.height:
            raise ProtocolValidationError(
                "Cannot finalize an uncommitted block."
            )

        if height < self.finalized_height:
            raise ProtocolValidationError(
                "Finality cannot move backwards."
            )

        if not valid_hash(block_hash):
            raise ProtocolValidationError(
                "Invalid finality block hash."
            )

        if not valid_hash(state_root):
            raise ProtocolValidationError(
                "Invalid finality state root."
            )

        if not valid_hash(validator_set_hash):
            raise ProtocolValidationError(
                "Invalid validator-set hash."
            )

        if height == 0 and self.finality:
            raise ProtocolValidationError(
                "Genesis finality already recorded."
            )

        timestamp = time.time() if timestamp is None else float(timestamp)

        checkpoint = FinalityCheckpoint(
            height=height,
            block_hash=block_hash,
            state_root=state_root,
            validator_set_hash=validator_set_hash,
            timestamp=timestamp,
        )

        if self.finality:
            previous = self.finality[-1]

            if checkpoint.height <= previous.height:
                raise ProtocolValidationError(
                    "Finality height must increase."
                )

        self.finality.append(checkpoint)

        if len(self.finality) > MAX_FINALITY_DEPTH:
            self.finality.pop(0)

        self._append_audit(
            event="FINALITY_CHECKPOINT",
            height=height,
            payload=checkpoint.to_dict(),
            timestamp=timestamp,
        )

        self._refresh_seal()

        return checkpoint

    # ------------------------------------------------------------------
    # SUPPLY / ECONOMIC INVARIANTS
    # ------------------------------------------------------------------

    def verify_supply(self, balances: Iterable[float]) -> tuple[bool, str]:
        total = 0.0

        for balance in balances:
            if balance < 0:
                return False, "Negative account balance detected."

            total += float(balance)

        if total > MAX_SUPPLY:
            return False, "Maximum supply exceeded."

        if abs(total - self.total_supply) > 1e-9:
            return (
                False,
                "Account balances do not match protocol total supply.",
            )

        return True, "Supply invariant is valid."

    # ------------------------------------------------------------------
    # INTEGRITY
    # ------------------------------------------------------------------

    def _calculate_seal(self) -> str:
        payload = {
            "protocol": self.identity.to_dict(),
            "height": self.height,
            "latest_block_hash": self.latest_block_hash,
            "latest_state_root": self.latest_state_root,
            "total_supply": self.total_supply,
            "finality": [
                item.to_dict()
                for item in self.finality
            ],
            "state_checkpoints": [
                item.to_dict()
                for item in self.state_checkpoints
            ],
            "validators": {
                address: observation.to_dict()
                for address, observation
                in sorted(self.validators.items())
            },
            "transaction_index": sorted(self.transaction_index),
            "contract_index": sorted(self.contract_index),
            "audit_root": self.audit_root,
        }

        return hash_object(payload)

    def _refresh_seal(self) -> None:
        self._seal = self._calculate_seal()

    def verify_integrity(self) -> tuple[bool, str]:
        for index, record in enumerate(self.audit_records):
            if not record.verify():
                return (
                    False,
                    f"Audit record {index} failed verification.",
                )

            if index > 0:
                previous = self.audit_records[index - 1]

                if record.previous_record_hash != previous.record_hash:
                    return (
                        False,
                        f"Audit chain broken at record {index}.",
                    )

        if self.height < 0:
            return False, "Invalid protocol height."

        if not valid_hash(self.latest_block_hash):
            return False, "Invalid latest block hash."

        if not valid_hash(self.latest_state_root):
            return False, "Invalid latest state root."

        if self.total_supply < 0:
            return False, "Negative total supply."

        if self.total_supply > MAX_SUPPLY:
            return False, "Maximum supply exceeded."

        if self.finality:
            previous_height = -1

            for checkpoint in self.finality:
                if checkpoint.height <= previous_height:
                    return (
                        False,
                        "Finality checkpoints are not monotonic.",
                    )

                if checkpoint.height > self.height:
                    return (
                        False,
                        "Finality exceeds committed height.",
                    )

                previous_height = checkpoint.height

        expected_seal = self._calculate_seal()

        if expected_seal != self._seal:
            return False, "Protocol integrity seal mismatch."

        return True, "Protocol core integrity is valid."

    # ------------------------------------------------------------------
    # SNAPSHOT
    # ------------------------------------------------------------------

    def snapshot(self) -> ProtocolCoreSnapshot:
        return ProtocolCoreSnapshot(
            height=self.height,
            latest_block_hash=self.latest_block_hash,
            latest_state_root=self.latest_state_root,
            total_supply=self.total_supply,
            finality=[
                item.to_dict()
                for item in self.finality
            ],
            state_checkpoints=[
                item.to_dict()
                for item in self.state_checkpoints
            ],
            validators={
                address: observation.to_dict()
                for address, observation
                in self.validators.items()
            },
            transaction_index=sorted(self.transaction_index),
            contract_index=sorted(self.contract_index),
            audit_records=[
                item.to_dict()
                for item in self.audit_records
            ],
            protocol_seal=self._seal,
        )

    def restore(self, snapshot: ProtocolCoreSnapshot) -> None:
        try:
            self.height = int(snapshot.height)
            self.latest_block_hash = str(
                snapshot.latest_block_hash
            )
            self.latest_state_root = str(
                snapshot.latest_state_root
            )
            self.total_supply = float(snapshot.total_supply)

            self.finality = [
                FinalityCheckpoint.from_dict(item)
                for item in snapshot.finality
            ]

            self.state_checkpoints = [
                StateCheckpoint(
                    height=int(item["height"]),
                    block_hash=str(item["block_hash"]),
                    state_root=str(item["state_root"]),
                    total_supply=float(item["total_supply"]),
                    account_count=int(item["account_count"]),
                    contract_count=int(item["contract_count"]),
                    timestamp=float(item["timestamp"]),
                )
                for item in snapshot.state_checkpoints
            ]

            self.validators = {
                address: ValidatorObservation.from_dict(data)
                for address, data
                in snapshot.validators.items()
            }

            self.transaction_index = set(
                snapshot.transaction_index
            )

            self.contract_index = set(
                snapshot.contract_index
            )

            self.audit_records = [
                AuditRecord.from_dict(item)
                for item in snapshot.audit_records
            ]

            self._seal = str(snapshot.protocol_seal)

        except Exception as exc:
            raise SnapshotError(
                f"Snapshot restoration failed: {exc}"
            ) from exc

        valid, reason = self.verify_integrity()

        if not valid:
            raise SnapshotError(
                f"Restored snapshot is invalid: {reason}"
            )

    # ------------------------------------------------------------------
    # HEALTH
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        integrity_valid, integrity_reason = self.verify_integrity()

        return {
            "protocol": self.identity.name,
            "protocol_version": self.identity.version,
            "protocol_id": self.protocol_id,
            "native_asset": self.identity.native_asset,
            "height": self.height,
            "finalized_height": self.finalized_height,
            "latest_block_hash": self.latest_block_hash,
            "latest_state_root": self.latest_state_root,
            "total_supply": self.total_supply,
            "max_supply": MAX_SUPPLY,
            "validator_count": self.validator_count,
            "transaction_count": self.transaction_count,
            "contract_count": self.contract_count,
            "audit_records": len(self.audit_records),
            "audit_root": self.audit_root,
            "integrity": integrity_valid,
            "integrity_reason": integrity_reason,
            "seal": self._seal,
        }

    # ------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "height": self.height,
            "latest_block_hash": self.latest_block_hash,
            "latest_state_root": self.latest_state_root,
            "total_supply": self.total_supply,
            "finality": [
                item.to_dict()
                for item in self.finality
            ],
            "state_checkpoints": [
                item.to_dict()
                for item in self.state_checkpoints
            ],
            "validators": {
                address: observation.to_dict()
                for address, observation
                in sorted(self.validators.items())
            },
            "transaction_index": sorted(
                self.transaction_index
            ),
            "contract_index": sorted(
                self.contract_index
            ),
            "audit_records": [
                item.to_dict()
                for item in self.audit_records
            ],
            "protocol_seal": self._seal,
        }

    def canonical_bytes(self) -> bytes:
        return canonical_json(self.to_dict()).encode("utf-8")

    def protocol_hash(self) -> str:
        return sha256_hex(self.canonical_bytes())

    # ------------------------------------------------------------------
    # STATS
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        return {
            "protocol": PROTOCOL_NAME,
            "version": PROTOCOL_VERSION,
            "height": self.height,
            "finalized_height": self.finalized_height,
            "validators": len(self.validators),
            "transactions": len(self.transaction_index),
            "contracts": len(self.contract_index),
            "state_checkpoints": len(self.state_checkpoints),
            "finality_checkpoints": len(self.finality),
            "audit_records": len(self.audit_records),
            "total_supply": self.total_supply,
            "protocol_hash": self.protocol_hash(),
            "integrity_seal": self._seal,
        }


# ============================================================================
# SELF TEST
# ============================================================================

def self_test() -> None:
    print("=" * 70)
    print("NEXCHAIN PROTOCOL CORE — STEP 20 TEST")
    print("=" * 70)

    validator_a = "NEX" + ("1" * 40)
    validator_b = "NEX" + ("2" * 40)

    # ------------------------------------------------------------------
    # 20A
    # ------------------------------------------------------------------

    core = ProtocolCore()

    assert core.protocol_id == "NEXCHAIN:1:NEX"
    assert core.height == 0
    assert core.total_supply == 0.0

    print("[PASS] 20A Protocol initialization")

    # ------------------------------------------------------------------
    # 20B
    # ------------------------------------------------------------------

    core.register_validator(validator_a)
    core.register_validator(validator_b)

    assert core.validator_count == 2
    assert validator_a in core.validators
    assert validator_b in core.validators

    print("[PASS] 20B Validator registry")

    # ------------------------------------------------------------------
    # 20C
    # ------------------------------------------------------------------

    core.record_block_proposed(validator_a)
    core.record_block_finalized(validator_a)
    core.record_block_proposed(validator_b)

    assert core.validators[validator_a].blocks_proposed == 1
    assert core.validators[validator_a].blocks_finalized == 1
    assert core.validators[validator_b].blocks_proposed == 1

    print("[PASS] 20C Validator observations")

    # ------------------------------------------------------------------
    # 20D
    # ------------------------------------------------------------------

    tx_hash_a = sha256_hex("transaction-A")
    tx_hash_b = sha256_hex("transaction-B")

    assert core.register_transaction(tx_hash_a)
    assert core.register_transaction(tx_hash_b)

    assert core.has_transaction(tx_hash_a)
    assert core.has_transaction(tx_hash_b)

    # Replay must be rejected.
    assert not core.register_transaction(tx_hash_a)

    assert core.transaction_count == 2

    print("[PASS] 20D Transaction replay protection")

    # ------------------------------------------------------------------
    # 20E
    # ------------------------------------------------------------------

    contract_a = "C" + ("a" * 42)
    contract_b = "C" + ("b" * 42)

    assert core.register_contract(contract_a)
    assert core.register_contract(contract_b)

    assert core.has_contract(contract_a)
    assert core.has_contract(contract_b)

    assert not core.register_contract(contract_a)

    assert core.contract_count == 2

    print("[PASS] 20E Contract registry")

    # ------------------------------------------------------------------
    # 20F
    # ------------------------------------------------------------------

    block_1 = sha256_hex("block-1")
    state_1 = sha256_hex("state-1")
    validator_set = sha256_hex(
        canonical_json(
            sorted(
                [validator_a, validator_b]
            )
        )
    )

    checkpoint = core.commit_block(
        height=1,
        block_hash=block_1,
        state_root=state_1,
        total_supply=1_000_000.0,
        account_count=5,
        contract_count=2,
        validator_set_hash=validator_set,
        timestamp=1700000010.0,
    )

    assert checkpoint.height == 1
    assert core.height == 1
    assert core.latest_block_hash == block_1
    assert core.latest_state_root == state_1
    assert core.total_supply == 1_000_000.0

    print("[PASS] 20F Block/state commitment")

    # ------------------------------------------------------------------
    # 20G
    # ------------------------------------------------------------------

    finality = core.finalize_block(
        height=1,
        block_hash=block_1,
        state_root=state_1,
        validator_set_hash=validator_set,
        timestamp=1700000011.0,
    )

    assert finality.height == 1
    assert core.finalized_height == 1

    print("[PASS] 20G Finality checkpoint")

    # ------------------------------------------------------------------
    # 20H
    # ------------------------------------------------------------------

    balances = [
        400_000.0,
        300_000.0,
        200_000.0,
        50_000.0,
        50_000.0,
    ]

    valid, reason = core.verify_supply(balances)

    assert valid, reason
    assert reason == "Supply invariant is valid."

    print("[PASS] 20H Supply invariant")

    # ------------------------------------------------------------------
    # 20I
    # ------------------------------------------------------------------

    valid, reason = core.verify_integrity()

    assert valid, reason

    print("[PASS] 20I Integrity verification")

    # ------------------------------------------------------------------
    # 20J
    # ------------------------------------------------------------------

    original_hash = core.protocol_hash()

    serialized = canonical_json(core.to_dict())
    assert serialized

    restored_data = json.loads(serialized)

    restored = ProtocolCore()

    snapshot = core.snapshot()
    restored.restore(snapshot)

    assert restored.protocol_hash() == original_hash
    assert restored.height == core.height
    assert restored.finalized_height == core.finalized_height
    assert restored.transaction_count == core.transaction_count
    assert restored.contract_count == core.contract_count

    print("[PASS] 20J Snapshot and deterministic serialization")

    # ------------------------------------------------------------------
    # 20K
    # ------------------------------------------------------------------

    health = core.health()

    assert health["protocol"] == "NEXCHAIN"
    assert health["native_asset"] == "NEX"
    assert health["height"] == 1
    assert health["finalized_height"] == 1
    assert health["integrity"] is True

    print("[PASS] 20K Protocol health")

    # ------------------------------------------------------------------
    # 20L
    # ------------------------------------------------------------------

    stats = core.stats()

    assert stats["height"] == 1
    assert stats["validators"] == 2
    assert stats["transactions"] == 2
    assert stats["contracts"] == 2
    assert stats["audit_records"] > 0
    assert len(stats["protocol_hash"]) == 64
    assert len(stats["integrity_seal"]) == 64

    print("[PASS] 20L Protocol statistics")

    # ------------------------------------------------------------------
    # 20M — tamper detection
    # ------------------------------------------------------------------

    tampered = core.snapshot()
    tampered.total_supply = 999_999.0

    try:
        restored.restore(tampered)
        raise AssertionError(
            "Tampered snapshot was incorrectly accepted."
        )
    except SnapshotError:
        pass

    print("[PASS] 20M Tamper detection")

    # ------------------------------------------------------------------
    # 20N — invalid supply
    # ------------------------------------------------------------------

    invalid, reason = core.verify_supply(
        [
            900_000.0,
            200_000.0,
        ]
    )

    assert not invalid
    assert "do not match" in reason

    print("[PASS] 20N Invalid supply detection")

    # ------------------------------------------------------------------
    # 20O — invalid validator
    # ------------------------------------------------------------------

    try:
        core.register_validator("INVALID")
        raise AssertionError(
            "Invalid validator was incorrectly accepted."
        )
    except ProtocolValidationError:
        pass

    print("[PASS] 20O Invalid validator protection")

    # ------------------------------------------------------------------
    # FINAL
    # ------------------------------------------------------------------

    final_valid, final_reason = core.verify_integrity()

    assert final_valid, final_reason

    print()
    print("=" * 70)
    print("NEXCHAIN PROTOCOL CORE — STEP 20 TEST: ALL PASSED")
    print("=" * 70)

    print()
    print("Protocol:", core.protocol_id)
    print("Height:", core.height)
    print("Finalized:", core.finalized_height)
    print("Validators:", core.validator_count)
    print("Transactions:", core.transaction_count)
    print("Contracts:", core.contract_count)
    print("Audit records:", len(core.audit_records))
    print("Protocol hash:", core.protocol_hash())
    print("Integrity seal:", core._seal)
    print()
    print("FINAL CORE LAYER READY")


if __name__ == "__main__":
    self_test()