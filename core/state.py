"""
NEXCHAIN — State Execution Engine
=================================

Account-based deterministic state management.

Features:
- Account creation
- Balance management
- Nonce management
- Cryptographic transaction validation
- Atomic transaction execution
- Snapshot / rollback
- Deterministic state root
- Serialization / restoration
- Supply invariants
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, Optional, Tuple

from crypto.crypto_engine import Wallet, canonical_json, sha256
from core.transaction import Transaction, create_transaction


# ============================================================
# EXCEPTIONS
# ============================================================

class StateError(Exception):
    """Base exception for NEXCHAIN state errors."""


class InvalidTransaction(StateError):
    """Raised when a transaction is invalid."""


class AccountNotFound(StateError):
    """Raised when an account does not exist."""


class StateInvariantError(StateError):
    """Raised when a state invariant is violated."""


# ============================================================
# ACCOUNT
# ============================================================

@dataclass
class Account:
    """
    NEXCHAIN account.

    Balance is represented in NEX units.
    Nonce increases after every successfully executed transaction.
    """

    address: str
    balance: float = 0.0
    nonce: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.address, str) or not self.address:
            raise ValueError("Account address must be a non-empty string.")

        if self.balance < 0:
            raise ValueError("Account balance cannot be negative.")

        if self.nonce < 0:
            raise ValueError("Account nonce cannot be negative.")

    def to_dict(self) -> dict:
        return {
            "address": self.address,
            "balance": self.balance,
            "nonce": self.nonce,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Account":
        return cls(
            address=data["address"],
            balance=float(data.get("balance", 0.0)),
            nonce=int(data.get("nonce", 0)),
        )


# ============================================================
# STATE ENGINE
# ============================================================

class StateEngine:
    """
    Deterministic account-state execution engine.
    """

    MAX_SUPPLY = 21_000_000_000.0

    def __init__(self) -> None:
        self.accounts: Dict[str, Account] = {}
        self.total_supply: float = 0.0

    # ========================================================
    # ACCOUNT MANAGEMENT
    # ========================================================

    def create_account(
        self,
        address: str,
        balance: float = 0.0,
        nonce: int = 0,
    ) -> Account:

        if not address:
            raise ValueError("Address cannot be empty.")

        if address in self.accounts:
            raise StateError(f"Account already exists: {address}")

        account = Account(
            address=address,
            balance=float(balance),
            nonce=int(nonce),
        )

        self.accounts[address] = account

        if balance != 0:
            self.total_supply += float(balance)
            self._check_supply()

        return account

    def get_account(self, address: str) -> Account:

        account = self.accounts.get(address)

        if account is None:
            raise AccountNotFound(
                f"Account not found: {address}"
            )

        return account

    def get_or_create_account(self, address: str) -> Account:

        account = self.accounts.get(address)

        if account is None:
            account = Account(address=address)
            self.accounts[address] = account

        return account

    def account_exists(self, address: str) -> bool:
        return address in self.accounts

    def balance_of(self, address: str) -> float:

        account = self.accounts.get(address)

        if account is None:
            return 0.0

        return account.balance

    def nonce_of(self, address: str) -> int:

        account = self.accounts.get(address)

        if account is None:
            return 0

        return account.nonce

    # ========================================================
    # SUPPLY
    # ========================================================

    def _calculate_supply(self) -> float:

        return sum(
            account.balance
            for account in self.accounts.values()
        )

    def _check_supply(self) -> None:

        calculated = self._calculate_supply()

        # Floating point values can accumulate tiny differences.
        if abs(calculated - self.total_supply) > 1e-9:
            raise StateInvariantError(
                "Supply mismatch: "
                f"recorded={self.total_supply}, "
                f"calculated={calculated}"
            )

        if calculated < -1e-9:
            raise StateInvariantError(
                "Total supply cannot be negative."
            )

        if calculated > self.MAX_SUPPLY + 1e-9:
            raise StateInvariantError(
                f"Maximum supply exceeded: "
                f"{calculated} > {self.MAX_SUPPLY}"
            )

    # ========================================================
    # TRANSACTION VALIDATION
    # ========================================================

    def validate_transaction(
        self,
        transaction: Transaction,
    ) -> Tuple[bool, str]:

        if not isinstance(transaction, Transaction):
            return False, "Invalid transaction object."

        if not transaction.sender:
            return False, "Missing sender."

        if not transaction.recipient:
            return False, "Missing recipient."

        if transaction.amount <= 0:
            return False, "Amount must be greater than zero."

        if transaction.fee < 0:
            return False, "Fee cannot be negative."

        if transaction.nonce < 0:
            return False, "Nonce cannot be negative."

        sender = self.accounts.get(transaction.sender)

        if sender is None:
            return False, "Sender account does not exist."

        # Cryptographic transaction validation.
        try:
            result = transaction.validate()

            if isinstance(result, tuple):
                cryptographically_valid = result[0]
                validation_reason = (
                    result[1] if len(result) > 1 else ""
                )

                if not cryptographically_valid:
                    return False, (
                        validation_reason
                        or "Cryptographic validation failed."
                    )

            elif result is not True:
                return False, (
                    "Cryptographic transaction validation failed."
                )

        except Exception as exc:
            return False, (
                f"Transaction validation error: {exc}"
            )

        # Nonce must exactly match account nonce.
        if transaction.nonce != sender.nonce:
            return (
                False,
                f"Invalid nonce: expected {sender.nonce}, "
                f"received {transaction.nonce}.",
            )

        required = (
            transaction.amount
            + transaction.fee
        )

        if sender.balance + 1e-12 < required:
            return (
                False,
                f"Insufficient balance: required {required}, "
                f"available {sender.balance}.",
            )

        return True, "OK"

    # ========================================================
    # TRANSACTION EXECUTION
    # ========================================================

    def apply_transaction(
        self,
        transaction: Transaction,
        fee_recipient: Optional[str] = None,
    ) -> None:

        valid, reason = self.validate_transaction(
            transaction
        )

        if not valid:
            raise InvalidTransaction(reason)

        sender = self.get_account(
            transaction.sender
        )

        recipient = self.get_or_create_account(
            transaction.recipient
        )

        fee_account = None

        if fee_recipient and transaction.fee > 0:
            fee_account = self.get_or_create_account(
                fee_recipient
            )

        total_cost = (
            transaction.amount
            + transaction.fee
        )

        sender.balance -= total_cost

        recipient.balance += transaction.amount

        sender.nonce += 1

        if fee_account is not None:
            fee_account.balance += transaction.fee

        self._check_supply()

    def apply_transactions(
        self,
        transactions: Iterable[Transaction],
        fee_recipient: Optional[str] = None,
    ) -> int:
        """
        Execute a batch atomically.

        Any failure restores the state exactly.
        """

        snapshot = self.snapshot()

        count = 0

        try:

            for transaction in transactions:

                self.apply_transaction(
                    transaction,
                    fee_recipient=fee_recipient,
                )

                count += 1

            self._check_supply()

            return count

        except Exception:

            self.restore(snapshot)

            raise

    # ========================================================
    # STATE ROOT
    # ========================================================

    def state_payload(self) -> dict:

        accounts = []

        for address in sorted(self.accounts):

            account = self.accounts[address]

            accounts.append(
                {
                    "address": account.address,
                    "balance": account.balance,
                    "nonce": account.nonce,
                }
            )

        return {
            "accounts": accounts,
            "total_supply": self.total_supply,
        }

    def state_root(self) -> str:

        payload = self.state_payload()

        return sha256(
            canonical_json(payload)
        )

    # ========================================================
    # SNAPSHOT
    # ========================================================

    def snapshot(self) -> dict:

        return {
            "accounts": {
                address: account.to_dict()
                for address, account
                in self.accounts.items()
            },
            "total_supply": self.total_supply,
        }

    def restore(self, snapshot: dict) -> None:

        accounts = snapshot.get(
            "accounts",
            {}
        )

        self.accounts = {
            address: Account.from_dict(data)
            for address, data
            in accounts.items()
        }

        self.total_supply = float(
            snapshot.get(
                "total_supply",
                0.0
            )
        )

        self._check_supply()

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict:

        return {
            "accounts": {
                address: account.to_dict()
                for address, account
                in sorted(
                    self.accounts.items()
                )
            },
            "total_supply": self.total_supply,
            "state_root": self.state_root(),
        }

    def serialize(self) -> dict:

        return self.to_dict()

    @classmethod
    def from_dict(
        cls,
        data: dict,
    ) -> "StateEngine":

        engine = cls()

        accounts = data.get(
            "accounts",
            {}
        )

        engine.accounts = {
            address: Account.from_dict(account_data)
            for address, account_data
            in accounts.items()
        }

        engine.total_supply = float(
            data.get(
                "total_supply",
                0.0
            )
        )

        engine._check_supply()

        expected_root = data.get(
            "state_root"
        )

        if expected_root is not None:

            actual_root = engine.state_root()

            if actual_root != expected_root:

                raise StateInvariantError(
                    "Serialized state-root verification failed."
                )

        return engine

    @classmethod
    def deserialize(
        cls,
        data: dict,
    ) -> "StateEngine":

        return cls.from_dict(data)

    # ========================================================
    # STATISTICS
    # ========================================================

    def stats(self) -> dict:

        nonzero_accounts = sum(
            1
            for account in self.accounts.values()
            if account.balance > 0
        )

        return {
            "accounts": len(self.accounts),
            "nonzero_accounts": nonzero_accounts,
            "total_supply": self.total_supply,
            "max_supply": self.MAX_SUPPLY,
            "state_root": self.state_root(),
        }

    # ========================================================
    # TRANSACTION FACTORY HELPER
    # ========================================================

    @staticmethod
    def create_test_transaction(
        wallet: Wallet,
        recipient: str,
        amount: float,
        fee: float,
        nonce: int,
    ) -> Transaction:
        """
        Create a genuine signed NEXCHAIN transaction.

        Uses the exact transaction factory API implemented
        in core.transaction.
        """

        return create_transaction(
            wallet=wallet,
            recipient=recipient,
            amount=amount,
            fee=fee,
            nonce=nonce,
        )


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 60)
    print("NEXCHAIN STATE ENGINE SELF-TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # WALLETS
    # --------------------------------------------------------

    alice_wallet = Wallet.generate()
    bob_wallet = Wallet.generate()
    miner_wallet = Wallet.generate()

    alice = alice_wallet.address()
    bob = bob_wallet.address()
    miner = miner_wallet.address()

    print("[PASS] Wallet generation")

    assert alice.startswith("NEX")
    assert bob.startswith("NEX")
    assert miner.startswith("NEX")

    assert len(alice) == 43
    assert len(bob) == 43
    assert len(miner) == 43

    print("[PASS] Address format")

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    state = StateEngine()

    state.create_account(
        alice,
        balance=1000.0,
    )

    state.create_account(
        bob,
        balance=100.0,
    )

    assert state.balance_of(alice) == 1000.0
    assert state.balance_of(bob) == 100.0
    assert state.total_supply == 1100.0

    print("[PASS] Account creation")
    print("[PASS] Initial balances")

    # --------------------------------------------------------
    # STATE ROOT
    # --------------------------------------------------------

    root_before = state.state_root()

    assert isinstance(root_before, str)
    assert len(root_before) == 64

    print("[PASS] Initial state root")

    # --------------------------------------------------------
    # SIGNED TRANSACTION
    # --------------------------------------------------------

    transaction = StateEngine.create_test_transaction(
        wallet=alice_wallet,
        recipient=bob,
        amount=250.0,
        fee=10.0,
        nonce=0,
    )

    valid, reason = state.validate_transaction(
        transaction
    )

    assert valid, reason

    print(
        "[PASS] Cryptographic transaction validation"
    )

    # --------------------------------------------------------
    # EXECUTE
    # --------------------------------------------------------

    state.apply_transaction(
        transaction,
        fee_recipient=miner,
    )

    assert abs(
        state.balance_of(alice) - 740.0
    ) < 1e-9

    assert abs(
        state.balance_of(bob) - 350.0
    ) < 1e-9

    assert abs(
        state.balance_of(miner) - 10.0
    ) < 1e-9

    assert state.nonce_of(alice) == 1

    assert abs(
        state.total_supply - 1100.0
    ) < 1e-9

    print("[PASS] Transaction execution")
    print("[PASS] Balance updates")
    print("[PASS] Nonce update")
    print("[PASS] Fee transfer")
    print("[PASS] Supply conservation")

    # --------------------------------------------------------
    # STATE ROOT TRANSITION
    # --------------------------------------------------------

    root_after = state.state_root()

    assert root_after != root_before
    assert len(root_after) == 64

    print("[PASS] State root transition")

    # --------------------------------------------------------
    # INVALID NONCE
    # --------------------------------------------------------

    bad_nonce_tx = StateEngine.create_test_transaction(
        wallet=alice_wallet,
        recipient=bob,
        amount=10.0,
        fee=1.0,
        nonce=0,
    )

    valid, reason = state.validate_transaction(
        bad_nonce_tx
    )

    assert not valid
    assert "nonce" in reason.lower()

    print("[PASS] Invalid nonce rejection")

    # --------------------------------------------------------
    # INSUFFICIENT BALANCE
    # --------------------------------------------------------

    huge_tx = StateEngine.create_test_transaction(
        wallet=alice_wallet,
        recipient=bob,
        amount=1_000_000.0,
        fee=1.0,
        nonce=1,
    )

    valid, reason = state.validate_transaction(
        huge_tx
    )

    assert not valid
    assert "balance" in reason.lower()

    print(
        "[PASS] Insufficient balance rejection"
    )

    # --------------------------------------------------------
    # ATOMIC ROLLBACK
    # --------------------------------------------------------

    rollback_snapshot = state.snapshot()

    valid_tx = StateEngine.create_test_transaction(
        wallet=alice_wallet,
        recipient=bob,
        amount=50.0,
        fee=2.0,
        nonce=1,
    )

    invalid_tx = StateEngine.create_test_transaction(
        wallet=alice_wallet,
        recipient=bob,
        amount=20.0,
        fee=1.0,
        nonce=999,
    )

    try:

        state.apply_transactions(
            [valid_tx, invalid_tx],
            fee_recipient=miner,
        )

        raise AssertionError(
            "Atomic batch should have failed."
        )

    except InvalidTransaction:
        pass

    assert (
        state.snapshot()
        == rollback_snapshot
    )

    print("[PASS] Atomic rollback")

    # --------------------------------------------------------
    # SNAPSHOT / RESTORE
    # --------------------------------------------------------

    snapshot = state.snapshot()

    state.get_account(
        alice
    ).balance -= 25.0

    state.get_account(
        bob
    ).balance += 25.0

    state.restore(snapshot)

    assert (
        state.snapshot()
        == snapshot
    )

    print("[PASS] Snapshot restore")

    # --------------------------------------------------------
    # SERIALIZATION
    # --------------------------------------------------------

    serialized = state.serialize()

    assert "accounts" in serialized
    assert "total_supply" in serialized
    assert "state_root" in serialized

    restored = StateEngine.deserialize(
        serialized
    )

    assert (
        restored.state_root()
        == state.state_root()
    )

    assert (
        abs(
            restored.total_supply
            - state.total_supply
        )
        < 1e-9
    )

    assert (
        restored.stats()
        == state.stats()
    )

    print("[PASS] Serialization")
    print("[PASS] State restoration")
    print("[PASS] State-root verification")

    # --------------------------------------------------------
    # STATISTICS
    # --------------------------------------------------------

    statistics = state.stats()

    assert statistics["accounts"] >= 3
    assert statistics["nonzero_accounts"] >= 3

    assert abs(
        statistics["total_supply"]
        - 1100.0
    ) < 1e-9

    assert (
        statistics["max_supply"]
        == StateEngine.MAX_SUPPLY
    )

    print("[PASS] State statistics")

    # --------------------------------------------------------
    # FINAL INVARIANT
    # --------------------------------------------------------

    state._check_supply()

    assert abs(
        state._calculate_supply()
        - state.total_supply
    ) < 1e-9

    print("[PASS] Final supply invariant")

    # --------------------------------------------------------
    # COMPLETE
    # --------------------------------------------------------

    print()
    print("=" * 60)
    print("NEXCHAIN STATE ENGINE SELF-TEST: PASSED")
    print("=" * 60)
    print()
    print(
        f"Accounts:     {len(state.accounts)}"
    )
    print(
        f"Total supply: {state.total_supply:,.4f} NEX"
    )
    print(
        f"State root:   {state.state_root()}"
    )
    print("=" * 60)


if __name__ == "__main__":
    self_test()