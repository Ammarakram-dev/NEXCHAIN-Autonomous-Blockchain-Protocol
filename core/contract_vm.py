"""
NEXCHAIN — Smart Contract Virtual Machine
Step 18: Deterministic Contract VM

Standalone execution engine.
No blockchain/state/network integration is performed here.
Integration is intentionally reserved for Step 19.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any


# ============================================================================
# CONSTANTS
# ============================================================================

VM_VERSION = 1
DEFAULT_GAS_LIMIT = 100_000
MAX_STACK_SIZE = 1024
MAX_MEMORY_SIZE = 4096
MAX_STORAGE_ITEMS = 1024
MAX_PROGRAM_SIZE = 4096

WORD_MIN = -(2**256)
WORD_MAX = 2**256 - 1


# ============================================================================
# EXCEPTIONS
# ============================================================================

class VMError(Exception):
    """Base VM exception."""


class InvalidProgram(VMError):
    """Program structure or opcode is invalid."""


class ExecutionError(VMError):
    """Runtime execution failure."""


class OutOfGas(VMError):
    """Execution exceeded the gas limit."""


class StackError(VMError):
    """Stack operation failure."""


class StorageError(VMError):
    """Contract storage failure."""


# ============================================================================
# OPCODES
# ============================================================================

class Opcode:
    STOP = "STOP"

    PUSH = "PUSH"
    POP = "POP"
    DUP = "DUP"
    SWAP = "SWAP"

    ADD = "ADD"
    SUB = "SUB"
    MUL = "MUL"
    DIV = "DIV"
    MOD = "MOD"
    NEG = "NEG"

    EQ = "EQ"
    LT = "LT"
    GT = "GT"
    LTE = "LTE"
    GTE = "GTE"

    AND = "AND"
    OR = "OR"
    XOR = "XOR"
    NOT = "NOT"

    JMP = "JMP"
    JZ = "JZ"
    JNZ = "JNZ"

    LOAD = "LOAD"
    STORE = "STORE"

    RETURN = "RETURN"
    REVERT = "REVERT"


VALID_OPCODES = {
    Opcode.STOP,
    Opcode.PUSH,
    Opcode.POP,
    Opcode.DUP,
    Opcode.SWAP,
    Opcode.ADD,
    Opcode.SUB,
    Opcode.MUL,
    Opcode.DIV,
    Opcode.MOD,
    Opcode.NEG,
    Opcode.EQ,
    Opcode.LT,
    Opcode.GT,
    Opcode.LTE,
    Opcode.GTE,
    Opcode.AND,
    Opcode.OR,
    Opcode.XOR,
    Opcode.NOT,
    Opcode.JMP,
    Opcode.JZ,
    Opcode.JNZ,
    Opcode.LOAD,
    Opcode.STORE,
    Opcode.RETURN,
    Opcode.REVERT,
}


# ============================================================================
# GAS SCHEDULE
# ============================================================================

GAS_COSTS = {
    Opcode.STOP: 0,

    Opcode.PUSH: 1,
    Opcode.POP: 1,
    Opcode.DUP: 1,
    Opcode.SWAP: 1,

    Opcode.ADD: 3,
    Opcode.SUB: 3,
    Opcode.MUL: 5,
    Opcode.DIV: 5,
    Opcode.MOD: 5,
    Opcode.NEG: 2,

    Opcode.EQ: 3,
    Opcode.LT: 3,
    Opcode.GT: 3,
    Opcode.LTE: 3,
    Opcode.GTE: 3,

    Opcode.AND: 3,
    Opcode.OR: 3,
    Opcode.XOR: 3,
    Opcode.NOT: 2,

    Opcode.JMP: 2,
    Opcode.JZ: 2,
    Opcode.JNZ: 2,

    Opcode.LOAD: 20,
    Opcode.STORE: 25,

    Opcode.RETURN: 0,
    Opcode.REVERT: 0,
}


# ============================================================================
# PROGRAM INSTRUCTION
# ============================================================================

@dataclass(frozen=True)
class Instruction:
    opcode: str
    operand: Any = None

    def __post_init__(self) -> None:
        if self.opcode not in VALID_OPCODES:
            raise InvalidProgram(f"Unknown opcode: {self.opcode}")

        if self.opcode in {
            Opcode.PUSH,
            Opcode.JMP,
            Opcode.JZ,
            Opcode.JNZ,
            Opcode.LOAD,
            Opcode.STORE,
        } and self.operand is None:
            raise InvalidProgram(
                f"Opcode {self.opcode} requires an operand."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "opcode": self.opcode,
            "operand": self.operand,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Instruction":
        return cls(
            opcode=str(data["opcode"]),
            operand=data.get("operand"),
        )


# ============================================================================
# PROGRAM
# ============================================================================

@dataclass(frozen=True)
class ContractProgram:
    instructions: tuple[Instruction, ...]
    version: int = VM_VERSION

    def __post_init__(self) -> None:
        if self.version != VM_VERSION:
            raise InvalidProgram(
                f"Unsupported VM version: {self.version}"
            )

        if len(self.instructions) == 0:
            raise InvalidProgram("Contract program cannot be empty.")

        if len(self.instructions) > MAX_PROGRAM_SIZE:
            raise InvalidProgram("Contract program is too large.")

        for instruction in self.instructions:
            if not isinstance(instruction, Instruction):
                raise InvalidProgram("Program contains an invalid instruction.")

        self._validate_jump_targets()

    def _validate_jump_targets(self) -> None:
        size = len(self.instructions)

        for index, instruction in enumerate(self.instructions):
            if instruction.opcode in {
                Opcode.JMP,
                Opcode.JZ,
                Opcode.JNZ,
            }:
                target = instruction.operand

                if not isinstance(target, int):
                    raise InvalidProgram(
                        f"Jump target at {index} must be an integer."
                    )

                if target < 0 or target >= size:
                    raise InvalidProgram(
                        f"Jump target {target} at {index} is out of bounds."
                    )

    def canonical_bytes(self) -> bytes:
        parts = [f"VM:{self.version}"]

        for instruction in self.instructions:
            if instruction.operand is None:
                parts.append(instruction.opcode)
            else:
                parts.append(
                    f"{instruction.opcode}:{repr(instruction.operand)}"
                )

        return "|".join(parts).encode("utf-8")

    def program_hash(self) -> str:
        return sha256(self.canonical_bytes()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "program_hash": self.program_hash(),
            "instructions": [
                instruction.to_dict()
                for instruction in self.instructions
            ],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ContractProgram":
        instructions = tuple(
            Instruction.from_dict(item)
            for item in data["instructions"]
        )

        program = cls(
            instructions=instructions,
            version=int(data.get("version", VM_VERSION)),
        )

        supplied_hash = data.get("program_hash")

        if supplied_hash is not None:
            if supplied_hash != program.program_hash():
                raise InvalidProgram("Program hash mismatch.")

        return program


# ============================================================================
# EXECUTION RESULT
# ============================================================================

@dataclass(frozen=True)
class ExecutionResult:
    success: bool
    return_data: tuple[int, ...]
    gas_used: int
    gas_remaining: int
    program_hash: str
    steps: int
    final_stack: tuple[int, ...]
    storage: dict[int, int]
    error: str | None = None
    reverted: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "return_data": list(self.return_data),
            "gas_used": self.gas_used,
            "gas_remaining": self.gas_remaining,
            "program_hash": self.program_hash,
            "steps": self.steps,
            "final_stack": list(self.final_stack),
            "storage": {
                str(key): value
                for key, value in sorted(self.storage.items())
            },
            "error": self.error,
            "reverted": self.reverted,
        }


# ============================================================================
# VM
# ============================================================================

@dataclass
class ContractVM:
    gas_limit: int = DEFAULT_GAS_LIMIT
    max_steps: int = 100_000

    stack: list[int] = field(default_factory=list)
    storage: dict[int, int] = field(default_factory=dict)

    pc: int = 0
    gas_used: int = 0
    steps: int = 0

    _halted: bool = False
    _success: bool = False
    _reverted: bool = False
    _return_data: list[int] = field(default_factory=list)
    _error: str | None = None

    def __post_init__(self) -> None:
        if self.gas_limit <= 0:
            raise ValueError("Gas limit must be positive.")

        if self.max_steps <= 0:
            raise ValueError("Maximum steps must be positive.")

    # ------------------------------------------------------------------------
    # WORD SAFETY
    # ------------------------------------------------------------------------

    @staticmethod
    def _normalize(value: int) -> int:
        if not isinstance(value, int):
            raise ExecutionError("VM values must be integers.")

        if value < WORD_MIN or value > WORD_MAX:
            raise ExecutionError("Integer exceeds VM word range.")

        return value

    # ------------------------------------------------------------------------
    # STACK
    # ------------------------------------------------------------------------

    def _push(self, value: int) -> None:
        if len(self.stack) >= MAX_STACK_SIZE:
            raise StackError("Stack overflow.")

        self.stack.append(self._normalize(value))

    def _pop(self) -> int:
        if not self.stack:
            raise StackError("Stack underflow.")

        return self.stack.pop()

    def _peek(self) -> int:
        if not self.stack:
            raise StackError("Stack underflow.")

        return self.stack[-1]

    # ------------------------------------------------------------------------
    # GAS
    # ------------------------------------------------------------------------

    @property
    def gas_remaining(self) -> int:
        return self.gas_limit - self.gas_used

    def _charge_gas(self, amount: int) -> None:
        if amount < 0:
            raise ExecutionError("Invalid gas amount.")

        if self.gas_used + amount > self.gas_limit:
            raise OutOfGas(
                f"Out of gas: required {amount}, "
                f"remaining {self.gas_remaining}."
            )

        self.gas_used += amount

    # ------------------------------------------------------------------------
    # STORAGE
    # ------------------------------------------------------------------------

    def _storage_key(self, value: Any) -> int:
        if not isinstance(value, int):
            raise StorageError("Storage key must be an integer.")

        if value < 0 or value > WORD_MAX:
            raise StorageError("Invalid storage key.")

        return value

    def _load(self, key: int) -> int:
        key = self._storage_key(key)
        return self.storage.get(key, 0)

    def _store(self, key: int, value: int) -> None:
        key = self._storage_key(key)
        value = self._normalize(value)

        if key not in self.storage:
            if len(self.storage) >= MAX_STORAGE_ITEMS:
                raise StorageError("Storage capacity exceeded.")

        self.storage[key] = value

    # ------------------------------------------------------------------------
    # EXECUTION
    # ------------------------------------------------------------------------

    def execute(
        self,
        program: ContractProgram,
        *,
        initial_stack: list[int] | None = None,
        initial_storage: dict[int, int] | None = None,
    ) -> ExecutionResult:

        if not isinstance(program, ContractProgram):
            raise InvalidProgram("Expected ContractProgram.")

        self.stack.clear()
        self.storage.clear()

        self.pc = 0
        self.gas_used = 0
        self.steps = 0

        self._halted = False
        self._success = False
        self._reverted = False
        self._return_data = []
        self._error = None

        if initial_stack is not None:
            if len(initial_stack) > MAX_STACK_SIZE:
                raise StackError("Initial stack is too large.")

            for value in initial_stack:
                self._push(value)

        if initial_storage is not None:
            if len(initial_storage) > MAX_STORAGE_ITEMS:
                raise StorageError("Initial storage is too large.")

            for key, value in initial_storage.items():
                self._store(int(key), int(value))

        try:
            while not self._halted:
                if self.steps >= self.max_steps:
                    raise ExecutionError("Maximum execution steps exceeded.")

                if self.pc < 0 or self.pc >= len(program.instructions):
                    raise ExecutionError(
                        f"Program counter out of bounds: {self.pc}"
                    )

                instruction = program.instructions[self.pc]

                self._charge_gas(
                    GAS_COSTS.get(instruction.opcode, 0)
                )

                current_pc = self.pc
                self.pc += 1
                self.steps += 1

                self._execute_instruction(instruction, current_pc)

        except VMError as exc:
            self._error = str(exc)
            self._halted = True
            self._success = False

            if isinstance(exc, OutOfGas):
                self.gas_used = self.gas_limit

        return ExecutionResult(
            success=self._success,
            return_data=tuple(self._return_data),
            gas_used=self.gas_used,
            gas_remaining=self.gas_remaining,
            program_hash=program.program_hash(),
            steps=self.steps,
            final_stack=tuple(self.stack),
            storage=dict(self.storage),
            error=self._error,
            reverted=self._reverted,
        )

    # ------------------------------------------------------------------------
    # OPCODE EXECUTION
    # ------------------------------------------------------------------------

    def _execute_instruction(
        self,
        instruction: Instruction,
        current_pc: int,
    ) -> None:

        opcode = instruction.opcode
        operand = instruction.operand

        if opcode == Opcode.STOP:
            self._success = True
            self._halted = True
            return

        if opcode == Opcode.PUSH:
            self._push(int(operand))
            return

        if opcode == Opcode.POP:
            self._pop()
            return

        if opcode == Opcode.DUP:
            self._push(self._peek())
            return

        if opcode == Opcode.SWAP:
            if len(self.stack) < 2:
                raise StackError("SWAP requires two stack values.")

            self.stack[-1], self.stack[-2] = (
                self.stack[-2],
                self.stack[-1],
            )
            return

        if opcode == Opcode.ADD:
            a = self._pop()
            b = self._pop()
            self._push(b + a)
            return

        if opcode == Opcode.SUB:
            a = self._pop()
            b = self._pop()
            self._push(b - a)
            return

        if opcode == Opcode.MUL:
            a = self._pop()
            b = self._pop()
            self._push(b * a)
            return

        if opcode == Opcode.DIV:
            a = self._pop()
            b = self._pop()

            if a == 0:
                raise ExecutionError("Division by zero.")

            self._push(b // a)
            return

        if opcode == Opcode.MOD:
            a = self._pop()
            b = self._pop()

            if a == 0:
                raise ExecutionError("Modulo by zero.")

            self._push(b % a)
            return

        if opcode == Opcode.NEG:
            self._push(-self._pop())
            return

        if opcode == Opcode.EQ:
            a = self._pop()
            b = self._pop()
            self._push(1 if b == a else 0)
            return

        if opcode == Opcode.LT:
            a = self._pop()
            b = self._pop()
            self._push(1 if b < a else 0)
            return

        if opcode == Opcode.GT:
            a = self._pop()
            b = self._pop()
            self._push(1 if b > a else 0)
            return

        if opcode == Opcode.LTE:
            a = self._pop()
            b = self._pop()
            self._push(1 if b <= a else 0)
            return

        if opcode == Opcode.GTE:
            a = self._pop()
            b = self._pop()
            self._push(1 if b >= a else 0)
            return

        if opcode == Opcode.AND:
            a = self._pop()
            b = self._pop()
            self._push(b & a)
            return

        if opcode == Opcode.OR:
            a = self._pop()
            b = self._pop()
            self._push(b | a)
            return

        if opcode == Opcode.XOR:
            a = self._pop()
            b = self._pop()
            self._push(b ^ a)
            return

        if opcode == Opcode.NOT:
            self._push(~self._pop())
            return

        if opcode == Opcode.JMP:
            self.pc = self._validate_jump(operand)
            return

        if opcode == Opcode.JZ:
            condition = self._pop()

            if condition == 0:
                self.pc = self._validate_jump(operand)

            return

        if opcode == Opcode.JNZ:
            condition = self._pop()

            if condition != 0:
                self.pc = self._validate_jump(operand)

            return

        if opcode == Opcode.LOAD:
            self._push(self._load(int(operand)))
            return

        if opcode == Opcode.STORE:
            value = self._pop()
            self._store(int(operand), value)
            return

        if opcode == Opcode.RETURN:
            count = 1 if operand is None else int(operand)

            if count < 0:
                raise ExecutionError("RETURN count cannot be negative.")

            if count > len(self.stack):
                raise StackError("RETURN exceeds stack size.")

            if count == 0:
                self._return_data = []
            else:
                self._return_data = list(self.stack[-count:])

            self._success = True
            self._halted = True
            return

        if opcode == Opcode.REVERT:
            self._reverted = True
            self._success = False
            self._halted = True

            if operand is None:
                raise ExecutionError("Contract execution reverted.")

            raise ExecutionError(
                f"Contract execution reverted: {operand}"
            )

        raise InvalidProgram(
            f"Unsupported opcode {opcode} at program counter {current_pc}."
        )

    @staticmethod
    def _validate_jump(target: Any) -> int:
        if not isinstance(target, int):
            raise ExecutionError("Jump target must be an integer.")

        if target < 0:
            raise ExecutionError("Jump target cannot be negative.")

        return target


# ============================================================================
# PROGRAM HELPERS
# ============================================================================

def program(*instructions: Instruction) -> ContractProgram:
    return ContractProgram(tuple(instructions))


def push(value: int) -> Instruction:
    return Instruction(Opcode.PUSH, value)


def jmp(target: int) -> Instruction:
    return Instruction(Opcode.JMP, target)


def jz(target: int) -> Instruction:
    return Instruction(Opcode.JZ, target)


def jnz(target: int) -> Instruction:
    return Instruction(Opcode.JNZ, target)


def load(key: int) -> Instruction:
    return Instruction(Opcode.LOAD, key)


def store(key: int) -> Instruction:
    return Instruction(Opcode.STORE, key)


# ============================================================================
# SELF TEST
# ============================================================================

def self_test() -> None:
    print("=" * 70)
    print("NEXCHAIN SMART CONTRACT VM — STEP 18 TEST")
    print("=" * 70)

    # ------------------------------------------------------------------------
    # 18A — VM initialization
    # ------------------------------------------------------------------------

    vm = ContractVM(gas_limit=1_000)

    assert vm.gas_limit == 1_000
    assert vm.gas_used == 0
    assert vm.stack == []
    assert vm.storage == {}

    # The storage object is intentionally a dictionary.
    assert isinstance(vm.storage, dict)

    print("[PASS] 18A VM initialization")

    # ------------------------------------------------------------------------
    # 18B — Program construction and hashing
    # ------------------------------------------------------------------------

    arithmetic = program(
        push(10),
        push(20),
        Instruction(Opcode.ADD),
        Instruction(Opcode.RETURN),
    )

    assert len(arithmetic.instructions) == 4
    assert len(arithmetic.program_hash()) == 64

    print("[PASS] 18B Program construction and hashing")

    # ------------------------------------------------------------------------
    # 18C — Arithmetic execution
    # ------------------------------------------------------------------------

    result = ContractVM(gas_limit=1_000).execute(arithmetic)

    assert result.success
    assert result.return_data == (30,)
    assert result.error is None
    assert result.gas_used > 0

    print("[PASS] 18C Arithmetic execution")

    # ------------------------------------------------------------------------
    # 18D — Comparison and logic
    # ------------------------------------------------------------------------

    comparison = program(
        push(50),
        push(25),
        Instruction(Opcode.GT),
        Instruction(Opcode.RETURN),
    )

    result = ContractVM(gas_limit=1_000).execute(comparison)

    assert result.success
    assert result.return_data == (1,)

    logic = program(
        push(12),
        push(10),
        Instruction(Opcode.AND),
        Instruction(Opcode.RETURN),
    )

    result = ContractVM(gas_limit=1_000).execute(logic)

    assert result.success
    assert result.return_data == (8,)

    print("[PASS] 18D Comparison and logic")

    # ------------------------------------------------------------------------
    # 18E — Persistent storage
    # ------------------------------------------------------------------------

    storage_program = program(
        push(777),
        store(1),
        load(1),
        Instruction(Opcode.RETURN),
    )

    result = ContractVM(gas_limit=1_000).execute(storage_program)

    assert result.success
    assert result.return_data == (777,)
    assert result.storage == {1: 777}

    print("[PASS] 18E Persistent VM storage")

    # ------------------------------------------------------------------------
    # 18F — Conditional branching
    # ------------------------------------------------------------------------

    branch_program = program(
        push(1),
        jz(5),
        push(123),
        Instruction(Opcode.RETURN),
        push(0),
        Instruction(Opcode.RETURN),
    )

    result = ContractVM(gas_limit=1_000).execute(branch_program)

    assert result.success
    assert result.return_data == (123,)

    print("[PASS] 18F Conditional branching")

    # ------------------------------------------------------------------------
    # 18G — Revert handling
    # ------------------------------------------------------------------------

    revert_program = program(
        push(99),
        Instruction(Opcode.REVERT, "intentional test revert"),
    )

    result = ContractVM(gas_limit=1_000).execute(revert_program)

    assert not result.success
    assert result.reverted
    assert result.error is not None
    assert "intentional test revert" in result.error

    print("[PASS] 18G Revert handling")

    # ------------------------------------------------------------------------
    # 18H — Out-of-gas protection
    # ------------------------------------------------------------------------

    expensive_program = program(
        push(1),
        push(2),
        Instruction(Opcode.MUL),
        Instruction(Opcode.MUL),
        Instruction(Opcode.MUL),
        Instruction(Opcode.RETURN),
    )

    result = ContractVM(gas_limit=4).execute(expensive_program)

    assert not result.success
    assert result.error is not None
    assert "Out of gas" in result.error

    print("[PASS] 18H Gas protection")

    # ------------------------------------------------------------------------
    # 18I — Serialization / deterministic program identity
    # ------------------------------------------------------------------------

    serialized = arithmetic.to_dict()
    restored = ContractProgram.from_dict(serialized)

    assert restored.program_hash() == arithmetic.program_hash()
    assert restored.to_dict() == serialized

    print("[PASS] 18I Deterministic serialization")

    # ------------------------------------------------------------------------
    # 18J — Full execution
    # ------------------------------------------------------------------------

    full_program = program(
        push(100),
        store(7),
        load(7),
        push(25),
        Instruction(Opcode.SUB),
        push(2),
        Instruction(Opcode.MUL),
        Instruction(Opcode.RETURN),
    )

    result = ContractVM(gas_limit=1_000).execute(full_program)

    assert result.success
    assert result.return_data == (150,)
    assert result.storage == {7: 100}
    assert result.gas_used > 0
    assert result.gas_remaining >= 0

    print("[PASS] 18J Complete smart contract execution")

    print("=" * 70)
    print("NEXCHAIN SMART CONTRACT VM — STEP 18 TEST: ALL PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()