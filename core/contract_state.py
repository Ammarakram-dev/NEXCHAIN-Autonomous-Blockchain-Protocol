"""
NEXCHAIN — Contract State & Execution Layer
Step 19

Builds on the standalone Step 18 Contract VM.

This module provides:
    - contract deployment
    - deterministic contract addresses
    - contract registry
    - contract storage
    - contract execution
    - execution receipts
    - gas accounting
    - snapshots and rollback
    - deterministic contract state root
    - serialization

Intentionally independent from:
    - Blockchain
    - Mempool
    - Consensus
    - P2P
    - RPC
    - CLI

Those integrations are reserved for Step 20.
"""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any

from core.contract_vm import (
    ContractProgram,
    ContractVM,
    DEFAULT_GAS_LIMIT,
    ExecutionResult,
)


# ============================================================================
# CONSTANTS
# ============================================================================

CONTRACT_STATE_VERSION = 1
CONTRACT_ADDRESS_PREFIX = "C"
CONTRACT_ADDRESS_LENGTH = 43

MAX_CONTRACTS = 10_000
MAX_CODE_SIZE = 4096
MAX_STORAGE_ITEMS = 1024

DEFAULT_DEPLOY_GAS = DEFAULT_GAS_LIMIT
DEFAULT_CALL_GAS = DEFAULT_GAS_LIMIT


# ============================================================================
# EXCEPTIONS
# ============================================================================

class ContractStateError(Exception):
    """Base contract-state exception."""


class ContractNotFound(ContractStateError):
    """Requested contract does not exist."""


class ContractAlreadyExists(ContractStateError):
    """Contract already exists."""


class InvalidContractAddress(ContractStateError):
    """Contract address is invalid."""


class DeploymentError(ContractStateError):
    """Contract deployment failed."""


class ContractExecutionError(ContractStateError):
    """Contract execution failed."""


class ContractStateLimitError(ContractStateError):
    """Contract-state limit was exceeded."""


# ============================================================================
# CANONICAL JSON
# ============================================================================

def _canonical_json(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


# ============================================================================
# CONTRACT ADDRESS
# ============================================================================

def derive_contract_address(
    deployer: str,
    program_hash: str,
    deployment_nonce: int,
) -> str:
    """
    Deterministically derive a contract address.

    Address:
        C + first 42 hexadecimal characters of SHA-256 digest
    """

    if not isinstance(deployer, str) or not deployer:
        raise InvalidContractAddress("Invalid deployer.")

    if not isinstance(program_hash, str) or len(program_hash) != 64:
        raise InvalidContractAddress("Invalid program hash.")

    if not isinstance(deployment_nonce, int) or deployment_nonce < 0:
        raise InvalidContractAddress("Invalid deployment nonce.")

    payload = (
        f"NEXCHAIN-CONTRACT:{deployer}:"
        f"{program_hash}:{deployment_nonce}"
    ).encode("utf-8")

    digest = sha256(payload).hexdigest()

    return CONTRACT_ADDRESS_PREFIX + digest[:42]


def validate_contract_address(address: str) -> bool:
    if not isinstance(address, str):
        return False

    if len(address) != CONTRACT_ADDRESS_LENGTH:
        return False

    if not address.startswith(CONTRACT_ADDRESS_PREFIX):
        return False

    return all(
        character in "0123456789abcdef"
        for character in address[1:]
    )


# ============================================================================
# CONTRACT RECORD
# ============================================================================

@dataclass
class Contract:
    address: str
    deployer: str
    program: ContractProgram
    deployment_nonce: int
    storage: dict[int, int]

    def __post_init__(self) -> None:
        if not validate_contract_address(self.address):
            raise InvalidContractAddress(self.address)

        if not isinstance(self.deployer, str) or not self.deployer:
            raise DeploymentError("Invalid contract deployer.")

        if not isinstance(self.program, ContractProgram):
            raise DeploymentError("Invalid contract program.")

        if not isinstance(self.deployment_nonce, int):
            raise DeploymentError("Invalid deployment nonce.")

        if self.deployment_nonce < 0:
            raise DeploymentError("Deployment nonce cannot be negative.")

        if len(self.storage) > MAX_STORAGE_ITEMS:
            raise ContractStateLimitError(
                "Contract storage capacity exceeded."
            )

        normalized_storage: dict[int, int] = {}

        for key, value in self.storage.items():
            if not isinstance(key, int):
                raise ContractStateError(
                    "Contract storage keys must be integers."
                )

            if not isinstance(value, int):
                raise ContractStateError(
                    "Contract storage values must be integers."
                )

            normalized_storage[key] = value

        self.storage = normalized_storage

    @property
    def program_hash(self) -> str:
        return self.program.program_hash()

    def code_hash(self) -> str:
        return self.program_hash

    def storage_root(self) -> str:
        payload = {
            "address": self.address,
            "storage": {
                str(key): value
                for key, value in sorted(self.storage.items())
            },
        }

        return sha256(_canonical_json(payload)).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "deployer": self.deployer,
            "program": self.program.to_dict(),
            "deployment_nonce": self.deployment_nonce,
            "storage": {
                str(key): value
                for key, value in sorted(self.storage.items())
            },
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Contract":
        storage = {
            int(key): int(value)
            for key, value in data.get("storage", {}).items()
        }

        return cls(
            address=str(data["address"]),
            deployer=str(data["deployer"]),
            program=ContractProgram.from_dict(data["program"]),
            deployment_nonce=int(data["deployment_nonce"]),
            storage=storage,
        )


# ============================================================================
# EXECUTION RECEIPT
# ============================================================================

@dataclass(frozen=True)
class ExecutionReceipt:
    success: bool
    contract_address: str
    operation: str
    program_hash: str
    gas_limit: int
    gas_used: int
    gas_remaining: int
    return_data: tuple[int, ...]
    state_root_before: str
    state_root_after: str
    storage_root_before: str
    storage_root_after: str
    reverted: bool
    error: str | None
    execution_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "contract_address": self.contract_address,
            "operation": self.operation,
            "program_hash": self.program_hash,
            "gas_limit": self.gas_limit,
            "gas_used": self.gas_used,
            "gas_remaining": self.gas_remaining,
            "return_data": list(self.return_data),
            "state_root_before": self.state_root_before,
            "state_root_after": self.state_root_after,
            "storage_root_before": self.storage_root_before,
            "storage_root_after": self.storage_root_after,
            "reverted": self.reverted,
            "error": self.error,
            "execution_id": self.execution_id,
        }


# ============================================================================
# SNAPSHOT
# ============================================================================

@dataclass(frozen=True)
class ContractStateSnapshot:
    contracts: dict[str, dict[str, Any]]
    deployment_nonces: dict[str, int]
    state_root: str


# ============================================================================
# CONTRACT STATE ENGINE
# ============================================================================

class ContractState:
    """
    Deterministic contract state manager.

    The object owns contract code and contract storage.
    """

    def __init__(self) -> None:
        self.contracts: dict[str, Contract] = {}
        self.deployment_nonces: dict[str, int] = {}
        self.receipts: list[ExecutionReceipt] = []

    # ------------------------------------------------------------------------
    # BASIC STATE
    # ------------------------------------------------------------------------

    @property
    def contract_count(self) -> int:
        return len(self.contracts)

    def has_contract(self, address: str) -> bool:
        return address in self.contracts

    def get_contract(self, address: str) -> Contract:
        contract = self.contracts.get(address)

        if contract is None:
            raise ContractNotFound(
                f"Contract not found: {address}"
            )

        return contract

    # ------------------------------------------------------------------------
    # DEPLOYMENT NONCE
    # ------------------------------------------------------------------------

    def next_deployment_nonce(self, deployer: str) -> int:
        return self.deployment_nonces.get(deployer, 0)

    # ------------------------------------------------------------------------
    # DEPLOYMENT
    # ------------------------------------------------------------------------

    def deploy(
        self,
        deployer: str,
        program: ContractProgram,
        *,
        initial_storage: dict[int, int] | None = None,
    ) -> Contract:
        if not isinstance(deployer, str) or not deployer:
            raise DeploymentError("Invalid deployer.")

        if not isinstance(program, ContractProgram):
            raise DeploymentError("Invalid contract program.")

        if len(self.contracts) >= MAX_CONTRACTS:
            raise ContractStateLimitError(
                "Maximum contract count reached."
            )

        program_bytes = program.canonical_bytes()

        if len(program_bytes) > MAX_CODE_SIZE:
            raise DeploymentError("Contract code is too large.")

        nonce = self.next_deployment_nonce(deployer)

        address = derive_contract_address(
            deployer,
            program.program_hash(),
            nonce,
        )

        if address in self.contracts:
            raise ContractAlreadyExists(address)

        storage = dict(initial_storage or {})

        if len(storage) > MAX_STORAGE_ITEMS:
            raise ContractStateLimitError(
                "Initial contract storage is too large."
            )

        contract = Contract(
            address=address,
            deployer=deployer,
            program=program,
            deployment_nonce=nonce,
            storage=storage,
        )

        self.contracts[address] = contract
        self.deployment_nonces[deployer] = nonce + 1

        return contract

    # ------------------------------------------------------------------------
    # CONTRACT STORAGE
    # ------------------------------------------------------------------------

    def read_storage(
        self,
        address: str,
        key: int,
    ) -> int:
        contract = self.get_contract(address)

        if not isinstance(key, int):
            raise ContractStateError(
                "Storage key must be an integer."
            )

        return contract.storage.get(key, 0)

    def write_storage(
        self,
        address: str,
        key: int,
        value: int,
    ) -> None:
        contract = self.get_contract(address)

        if not isinstance(key, int):
            raise ContractStateError(
                "Storage key must be an integer."
            )

        if not isinstance(value, int):
            raise ContractStateError(
                "Storage value must be an integer."
            )

        if key not in contract.storage:
            if len(contract.storage) >= MAX_STORAGE_ITEMS:
                raise ContractStateLimitError(
                    "Contract storage capacity exceeded."
                )

        contract.storage[key] = value

    # ------------------------------------------------------------------------
    # STATE ROOT
    # ------------------------------------------------------------------------

    def state_payload(self) -> dict[str, Any]:
        return {
            "version": CONTRACT_STATE_VERSION,
            "contracts": {
                address: contract.to_dict()
                for address, contract in sorted(self.contracts.items())
            },
            "deployment_nonces": {
                deployer: nonce
                for deployer, nonce in sorted(
                    self.deployment_nonces.items()
                )
            },
        }

    def state_root(self) -> str:
        return sha256(
            _canonical_json(self.state_payload())
        ).hexdigest()

    # ------------------------------------------------------------------------
    # SNAPSHOT / ROLLBACK
    # ------------------------------------------------------------------------

    def snapshot(self) -> ContractStateSnapshot:
        contracts = {
            address: deepcopy(contract.to_dict())
            for address, contract in self.contracts.items()
        }

        return ContractStateSnapshot(
            contracts=contracts,
            deployment_nonces=deepcopy(
                self.deployment_nonces
            ),
            state_root=self.state_root(),
        )

    def restore(self, snapshot: ContractStateSnapshot) -> None:
        restored_contracts: dict[str, Contract] = {}

        for address, data in snapshot.contracts.items():
            restored_contracts[address] = Contract.from_dict(data)

        self.contracts = restored_contracts
        self.deployment_nonces = deepcopy(
            snapshot.deployment_nonces
        )

        if self.state_root() != snapshot.state_root:
            raise ContractStateError(
                "Snapshot restoration root mismatch."
            )

    # ------------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------------

    def call(
        self,
        address: str,
        *,
        gas_limit: int = DEFAULT_CALL_GAS,
        initial_stack: list[int] | None = None,
    ) -> ExecutionReceipt:

        contract = self.get_contract(address)

        if gas_limit <= 0:
            raise ContractExecutionError(
                "Gas limit must be positive."
            )

        state_before = self.state_root()
        storage_before = contract.storage_root()

        snapshot = self.snapshot()

        vm = ContractVM(gas_limit=gas_limit)

        result: ExecutionResult = vm.execute(
            contract.program,
            initial_stack=initial_stack,
            initial_storage=contract.storage,
        )

        if result.success:
            contract.storage = dict(result.storage)
            state_after = self.state_root()
            storage_after = contract.storage_root()
        else:
            self.restore(snapshot)
            contract = self.get_contract(address)

            state_after = self.state_root()
            storage_after = contract.storage_root()

        execution_id = self._execution_id(
            contract_address=address,
            operation="CALL",
            program_hash=contract.program_hash,
            gas_used=result.gas_used,
            state_before=state_before,
            state_after=state_after,
        )

        receipt = ExecutionReceipt(
            success=result.success,
            contract_address=address,
            operation="CALL",
            program_hash=contract.program_hash,
            gas_limit=gas_limit,
            gas_used=result.gas_used,
            gas_remaining=result.gas_remaining,
            return_data=result.return_data,
            state_root_before=state_before,
            state_root_after=state_after,
            storage_root_before=storage_before,
            storage_root_after=storage_after,
            reverted=result.reverted,
            error=result.error,
            execution_id=execution_id,
        )

        self.receipts.append(receipt)

        return receipt

    # ------------------------------------------------------------------------
    # EXECUTION WITH MUTABLE CALL STATE
    # ------------------------------------------------------------------------

    def execute_with_stack(
        self,
        address: str,
        stack: list[int],
        *,
        gas_limit: int = DEFAULT_CALL_GAS,
    ) -> ExecutionReceipt:

        return self.call(
            address,
            gas_limit=gas_limit,
            initial_stack=stack,
        )

    # ------------------------------------------------------------------------
    # RECEIPTS
    # ------------------------------------------------------------------------

    def latest_receipt(self) -> ExecutionReceipt | None:
        if not self.receipts:
            return None

        return self.receipts[-1]

    # ------------------------------------------------------------------------
    # EXECUTION ID
    # ------------------------------------------------------------------------

    @staticmethod
    def _execution_id(
        *,
        contract_address: str,
        operation: str,
        program_hash: str,
        gas_used: int,
        state_before: str,
        state_after: str,
    ) -> str:

        payload = (
            f"{contract_address}|"
            f"{operation}|"
            f"{program_hash}|"
            f"{gas_used}|"
            f"{state_before}|"
            f"{state_after}"
        ).encode("utf-8")

        return sha256(payload).hexdigest()

    # ------------------------------------------------------------------------
    # SERIALIZATION
    # ------------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": CONTRACT_STATE_VERSION,
            "contracts": {
                address: contract.to_dict()
                for address, contract in sorted(self.contracts.items())
            },
            "deployment_nonces": {
                deployer: nonce
                for deployer, nonce in sorted(
                    self.deployment_nonces.items()
                )
            },
            "state_root": self.state_root(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContractState":
        state = cls()

        if int(data.get("version", CONTRACT_STATE_VERSION)) != (
            CONTRACT_STATE_VERSION
        ):
            raise ContractStateError(
                "Unsupported contract state version."
            )

        for address, contract_data in data.get(
            "contracts", {}
        ).items():
            contract = Contract.from_dict(contract_data)

            if contract.address != address:
                raise ContractStateError(
                    "Contract address mismatch."
                )

            state.contracts[address] = contract

        state.deployment_nonces = {
            str(deployer): int(nonce)
            for deployer, nonce in data.get(
                "deployment_nonces", {}
            ).items()
        }

        supplied_root = data.get("state_root")

        if supplied_root is not None:
            if supplied_root != state.state_root():
                raise ContractStateError(
                    "Contract state root mismatch."
                )

        return state

    # ------------------------------------------------------------------------
    # STATS
    # ------------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        storage_items = sum(
            len(contract.storage)
            for contract in self.contracts.values()
        )

        return {
            "version": CONTRACT_STATE_VERSION,
            "contracts": len(self.contracts),
            "storage_items": storage_items,
            "receipts": len(self.receipts),
            "state_root": self.state_root(),
        }


# ============================================================================
# SELF TEST
# ============================================================================

def self_test() -> None:
    print("=" * 70)
    print("NEXCHAIN CONTRACT STATE & EXECUTION — STEP 19 TEST")
    print("=" * 70)

    deployer = "NEX" + ("1" * 40)

    # ------------------------------------------------------------------------
    # 19A — Initialization
    # ------------------------------------------------------------------------

    state = ContractState()

    assert state.contract_count == 0
    assert state.state_root()
    assert len(state.state_root()) == 64

    print("[PASS] 19A Contract state initialization")

    # ------------------------------------------------------------------------
    # 19B — Contract program
    # ------------------------------------------------------------------------


    # Build the actual Step 18 instructions without introducing
    # any additional dependency.
    from core.contract_vm import (
        Instruction,
        Opcode,
        push,
        store,
        load,
    )


    program = ContractProgram(
        (
            push(500),
            store(1),
            load(1),
            push(250),
            Instruction(Opcode.ADD),
            Instruction(Opcode.RETURN),
        )
    )
    assert len(program.instructions) == 6
    assert len(program.program_hash()) == 64

    print("[PASS] 19B Contract program preparation")

    # ------------------------------------------------------------------------
    # 19C — Deployment
    # ------------------------------------------------------------------------

    contract = state.deploy(
        deployer,
        program,
    )

    assert state.contract_count == 1
    assert validate_contract_address(contract.address)
    assert contract.deployer == deployer
    assert contract.program_hash == program.program_hash()

    print("[PASS] 19C Contract deployment")

    # ------------------------------------------------------------------------
    # 19D — Deterministic address
    # ------------------------------------------------------------------------

    expected_address = derive_contract_address(
        deployer,
        program.program_hash(),
        0,
    )

    assert contract.address == expected_address

    second_address = derive_contract_address(
        deployer,
        program.program_hash(),
        1,
    )

    assert second_address != contract.address

    print("[PASS] 19D Deterministic contract addresses")

    # ------------------------------------------------------------------------
    # 19E — Initial storage
    # ------------------------------------------------------------------------

    initial_value = state.read_storage(
        contract.address,
        999,
    )

    assert initial_value == 0

    state.write_storage(
        contract.address,
        999,
        42,
    )

    assert state.read_storage(
        contract.address,
        999,
    ) == 42

    print("[PASS] 19E Contract storage")

    # ------------------------------------------------------------------------
    # 19F — Successful execution
    # ------------------------------------------------------------------------

    root_before = state.state_root()

    receipt = state.call(
        contract.address,
        gas_limit=10_000,
    )

    assert receipt.success
    assert not receipt.reverted
    assert receipt.error is None
    assert receipt.return_data == (750,)
    assert receipt.gas_used > 0
    assert receipt.gas_remaining >= 0
    assert len(receipt.execution_id) == 64

    root_after = state.state_root()

    assert receipt.state_root_before == root_before
    assert receipt.state_root_after == root_after

    print("[PASS] 19F Contract execution")

    # ------------------------------------------------------------------------
    # 19G — Storage persistence after execution
    # ------------------------------------------------------------------------

    assert state.read_storage(
        contract.address,
        1,
    ) == 500

    assert state.read_storage(
        contract.address,
        999,
    ) == 42

    print("[PASS] 19G Execution state persistence")

    # ------------------------------------------------------------------------
    # 19H — Snapshot and rollback
    # ------------------------------------------------------------------------

    snapshot = state.snapshot()
    snapshot_root = state.state_root()

    state.write_storage(
        contract.address,
        999,
        9999,
    )

    assert state.read_storage(
        contract.address,
        999,
    ) == 9999

    assert state.state_root() != snapshot_root

    state.restore(snapshot)

    assert state.read_storage(
        contract.address,
        999,
    ) == 42

    assert state.state_root() == snapshot_root

    print("[PASS] 19H Snapshot and rollback")

    # ------------------------------------------------------------------------
    # 19I — Revert rollback
    # ------------------------------------------------------------------------

    from core.contract_vm import Instruction as VMInstruction

    revert_program = ContractProgram(
        (
            push(1234),
            store(55),
            VMInstruction(
                Opcode.REVERT,
                "step 19 rollback test",
            ),
        )
    )

    revert_contract = state.deploy(
        deployer,
        revert_program,
    )

    revert_before = state.state_root()

    revert_receipt = state.call(
        revert_contract.address,
        gas_limit=10_000,
    )

    assert not revert_receipt.success
    assert revert_receipt.reverted
    assert revert_receipt.error is not None

    assert state.read_storage(
        revert_contract.address,
        55,
    ) == 0

    assert state.state_root() == revert_before

    print("[PASS] 19I Revert and atomic rollback")

    # ------------------------------------------------------------------------
    # 19J — Serialization
    # ------------------------------------------------------------------------

    serialized = state.to_dict()

    restored = ContractState.from_dict(
        serialized
    )

    assert restored.state_root() == state.state_root()
    assert restored.contract_count == state.contract_count

    restored_contract = restored.get_contract(
        contract.address
    )

    assert restored_contract.program_hash == (
        contract.program_hash
    )

    assert restored.read_storage(
        contract.address,
        1,
    ) == 500

    assert restored.read_storage(
        contract.address,
        999,
    ) == 42

    print("[PASS] 19J Deterministic serialization")

    # ------------------------------------------------------------------------
    # 19K — Complete state/execution verification
    # ------------------------------------------------------------------------

    stats = state.stats()

    assert stats["contracts"] == 2
    assert stats["storage_items"] >= 2
    assert stats["receipts"] >= 2
    assert len(stats["state_root"]) == 64

    latest = state.latest_receipt()

    assert latest is not None
    assert len(latest.execution_id) == 64

    print("[PASS] 19K Complete contract state system")

    print("=" * 70)
    print(
        "NEXCHAIN CONTRACT STATE & EXECUTION — "
        "STEP 19 TEST: ALL PASSED"
    )
    print("=" * 70)


if __name__ == "__main__":
    self_test()
