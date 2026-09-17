from __future__ import annotations

import hashlib
import json
import math
import os
import sqlite3
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from core.transaction import Transaction


# ======================================================================
# NEXCHAIN MEMPOOL
# 16A - Mempool Engine
# 16B - Transaction Admission & Validation
# 16C - Fee-Based Transaction Selection
# 16D - Nonce Management
# 16E - Duplicate / Replay Protection
# 16F - Persistent Mempool Storage
# 16G - P2P Transaction Propagation
# 16H - Full Integration Tests
# ======================================================================


DEFAULT_MAX_TRANSACTIONS = 10_000
DEFAULT_MAX_TRANSACTIONS_PER_SENDER = 100
MIN_MEMPOOL_FEE = 0.00000001
MEMPOOL_STORE_VERSION = 1
P2P_MESSAGE_TYPE = "new_transaction"


# ======================================================================
# ERRORS
# ======================================================================


class MempoolError(Exception):
    """Base mempool exception."""


class TransactionRejected(MempoolError):
    """Raised when a transaction cannot be admitted."""


class MempoolPersistenceError(MempoolError):
    """Raised when persistent mempool storage fails."""


# ======================================================================
# HELPERS
# ======================================================================


def _canonical_json(value: Any) -> str:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _safe_float(value: Any, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be numeric.") from exc

    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite.")

    return result


# ======================================================================
# MEMPOOL ENTRY
# ======================================================================


@dataclass(frozen=True)
class MempoolEntry:
    transaction: Transaction
    received_at: float

    @property
    def transaction_hash(self) -> str:
        return self.transaction.transaction_hash()

    @property
    def sender(self) -> str:
        return self.transaction.sender

    @property
    def nonce(self) -> int:
        return int(self.transaction.nonce)

    @property
    def fee(self) -> float:
        return float(self.transaction.fee)

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction": self.transaction.to_dict(),
            "received_at": self.received_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "MempoolEntry":
        if not isinstance(data, dict):
            raise ValueError("Mempool entry must be a dictionary.")

        transaction = Transaction.from_dict(data["transaction"])
        received_at = _safe_float(data["received_at"], "received_at")

        if received_at <= 0:
            raise ValueError("received_at must be positive.")

        return cls(
            transaction=transaction,
            received_at=received_at,
        )


# ======================================================================
# MEMPOOL ENGINE
# ======================================================================


class Mempool:
    """
    Thread-safe pending transaction pool.

    Core guarantees:
    - transaction hash uniqueness
    - sender/nonce conflict protection
    - fee validation
    - sender limits
    - total pool capacity
    - deterministic fee ordering
    - executable nonce ordering
    - replay protection
    - confirmed nonce tracking
    """

    def __init__(
        self,
        max_transactions: int = DEFAULT_MAX_TRANSACTIONS,
        max_transactions_per_sender: int = DEFAULT_MAX_TRANSACTIONS_PER_SENDER,
        min_fee: float = MIN_MEMPOOL_FEE,
    ):
        if max_transactions <= 0:
            raise ValueError("max_transactions must be positive.")

        if max_transactions_per_sender <= 0:
            raise ValueError(
                "max_transactions_per_sender must be positive."
            )

        min_fee = _safe_float(min_fee, "min_fee")

        if min_fee < 0:
            raise ValueError("min_fee cannot be negative.")

        self.max_transactions = int(max_transactions)
        self.max_transactions_per_sender = int(
            max_transactions_per_sender
        )
        self.min_fee = min_fee

        self._entries: dict[str, MempoolEntry] = {}

        # sender -> nonce -> tx hash
        self._sender_nonces: dict[str, dict[int, str]] = {}

        # Highest confirmed nonce known for every sender.
        self._confirmed_nonces: dict[str, int] = {}

        # Transaction hashes that have already been accepted/seen.
        self._seen_hashes: set[str] = set()

        # Permanently protected hashes for confirmed transactions.
        self._confirmed_hashes: set[str] = set()

        self._lock = threading.RLock()

        self._accepted_count = 0
        self._rejected_count = 0
        self._removed_count = 0
        self._replaced_count = 0

    # ------------------------------------------------------------------
    # Basic properties
    # ------------------------------------------------------------------

    def __len__(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def size(self) -> int:
        return len(self)

    @property
    def capacity(self) -> int:
        return self.max_transactions

    @property
    def remaining_capacity(self) -> int:
        with self._lock:
            return max(
                0,
                self.max_transactions - len(self._entries),
            )

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------

    def contains(self, transaction_hash: str) -> bool:
        with self._lock:
            return transaction_hash in self._entries

    def get(self, transaction_hash: str) -> Transaction | None:
        with self._lock:
            entry = self._entries.get(transaction_hash)
            return entry.transaction if entry else None

    def get_entry(self, transaction_hash: str) -> MempoolEntry | None:
        with self._lock:
            return self._entries.get(transaction_hash)

    def get_all(self) -> list[Transaction]:
        with self._lock:
            entries = sorted(
                self._entries.values(),
                key=lambda entry: (
                    -entry.fee,
                    entry.received_at,
                    entry.transaction_hash,
                ),
            )

            return [entry.transaction for entry in entries]

    def get_entries(self) -> list[MempoolEntry]:
        with self._lock:
            return list(self._entries.values())

    def get_sender_transactions(
        self,
        sender: str,
    ) -> list[Transaction]:
        with self._lock:
            sender_entries = [
                entry
                for entry in self._entries.values()
                if entry.sender == sender
            ]

            sender_entries.sort(
                key=lambda entry: (
                    entry.nonce,
                    entry.received_at,
                    entry.transaction_hash,
                )
            )

            return [
                entry.transaction
                for entry in sender_entries
            ]

    def sender_size(self, sender: str) -> int:
        with self._lock:
            return sum(
                1
                for entry in self._entries.values()
                if entry.sender == sender
            )

    def transaction_hashes(self) -> list[str]:
        with self._lock:
            return sorted(self._entries.keys())

    # ------------------------------------------------------------------
    # Nonce management
    # ------------------------------------------------------------------

    def confirmed_nonce(self, sender: str) -> int:
        with self._lock:
            return self._confirmed_nonces.get(sender, -1)

    def set_confirmed_nonce(
        self,
        sender: str,
        nonce: int,
    ) -> None:
        if not isinstance(sender, str) or not sender:
            raise ValueError("sender must be a non-empty string.")

        nonce = int(nonce)

        if nonce < 0:
            raise ValueError("confirmed nonce cannot be negative.")

        with self._lock:
            current = self._confirmed_nonces.get(sender, -1)

            if nonce < current:
                raise ValueError(
                    "Confirmed nonce cannot move backwards."
                )

            self._confirmed_nonces[sender] = nonce

            # Remove stale pending transactions.
            stale = [
                tx_hash
                for tx_hash, entry in self._entries.items()
                if entry.sender == sender
                and entry.nonce <= nonce
            ]

            for tx_hash in stale:
                self._remove_hash_locked(
                    tx_hash,
                    count_removed=True,
                )

    def advance_confirmed_nonce(
        self,
        sender: str,
        nonce: int,
    ) -> None:
        self.set_confirmed_nonce(sender, nonce)

    def next_expected_nonce(self, sender: str) -> int:
        with self._lock:
            nonce = self._confirmed_nonces.get(sender, -1) + 1

            sender_nonces = self._sender_nonces.get(
                sender,
                {},
            )

            while nonce in sender_nonces:
                nonce += 1

            return nonce

    def is_nonce_available(
        self,
        sender: str,
        nonce: int,
    ) -> bool:
        with self._lock:
            confirmed = self._confirmed_nonces.get(
                sender,
                0,
            )

            if nonce <= confirmed:
                return False

            return nonce not in self._sender_nonces.get(
                sender,
                {},
            )

    # ------------------------------------------------------------------
    # Replay protection
    # ------------------------------------------------------------------

    def has_seen(self, transaction_hash: str) -> bool:
        if not isinstance(transaction_hash, str):
            return False

        transaction_hash = transaction_hash.strip().lower()

        with self._lock:
            return transaction_hash in self._seen_hashes

    def mark_seen(self, transaction_hash: str) -> bool:
        """
        Record a transaction hash as seen.

        Returns:
            True  -> newly recorded
            False -> already known
        """
        if not isinstance(transaction_hash, str):
            raise TypeError(
                "transaction_hash must be a string."
            )

        transaction_hash = transaction_hash.strip().lower()

        if not transaction_hash:
            raise ValueError(
                "transaction_hash cannot be empty."
            )

        with self._lock:
            if transaction_hash in self._seen_hashes:
                return False

            self._seen_hashes.add(transaction_hash)
            return True

    def is_replay_protected(
        self,
        transaction_hash: str,
    ) -> bool:
        if not isinstance(transaction_hash, str):
            return False

        transaction_hash = transaction_hash.strip().lower()

        with self._lock:
            return (
                transaction_hash in self._seen_hashes
                or transaction_hash in self._confirmed_hashes
            )

    def is_confirmed_hash(
        self,
        transaction_hash: str,
    ) -> bool:
        with self._lock:
            return transaction_hash in self._confirmed_hashes

    # ------------------------------------------------------------------
    # Admission validation
    # ------------------------------------------------------------------

    def _validate_admission_locked(
        self,
        transaction: Transaction,
    ) -> tuple[bool, str]:
        if not isinstance(transaction, Transaction):
            return False, "Object is not a Transaction."

        try:
            valid, reason = transaction.validate()
        except Exception as exc:
            return False, f"Transaction validation failed: {exc}"

        if not valid:
            return False, reason

        tx_hash = transaction.transaction_hash()

        if not tx_hash:
            return False, "Transaction hash is empty."

        if tx_hash in self._confirmed_hashes:
            return False, "Transaction is replay protected."

        if tx_hash in self._entries:
            return False, "Duplicate transaction."

        fee = float(transaction.fee)

        if not math.isfinite(fee):
            return False, "Transaction fee must be finite."

        if fee < self.min_fee:
            return False, (
                f"Transaction fee below mempool minimum "
                f"({self.min_fee})."
            )

        sender = transaction.sender
        nonce = int(transaction.nonce)

        confirmed_nonce = self._confirmed_nonces.get(
            sender,
            -1,
        )

        if nonce <= confirmed_nonce:
            return False, (
                f"Nonce {nonce} is already confirmed. "
                f"Highest confirmed nonce is "
                f"{confirmed_nonce}."
            )

        sender_nonces = self._sender_nonces.get(
            sender,
            {},
        )

        if nonce in sender_nonces:
            return False, (
                f"Sender nonce conflict: "
                f"{sender}:{nonce}."
            )

        sender_count = len(sender_nonces)

        if sender_count >= self.max_transactions_per_sender:
            return False, (
                "Sender mempool limit reached."
            )

        return True, "Transaction accepted."

    def validate_admission(
        self,
        transaction: Transaction,
    ) -> tuple[bool, str]:
        with self._lock:
            return self._validate_admission_locked(
                transaction
            )

    # ------------------------------------------------------------------
    # Add transaction
    # ------------------------------------------------------------------

    def add(
        self,
        transaction: Transaction,
        received_at: float | None = None,
        allow_replacement: bool = True,
    ) -> tuple[bool, str]:
        """
        Atomically validate and add a transaction.

        If the mempool is full, a higher-fee transaction may replace
        the lowest-fee transaction when allow_replacement=True.
        """
        with self._lock:
            valid, reason = self._validate_admission_locked(
                transaction
            )

            if not valid:
                self._rejected_count += 1
                return False, reason

            if received_at is None:
                received_at = time.time()

            received_at = _safe_float(
                received_at,
                "received_at",
            )

            if received_at <= 0:
                self._rejected_count += 1
                return False, "received_at must be positive."

            tx_hash = transaction.transaction_hash()

            # Capacity handling.
            if len(self._entries) >= self.max_transactions:
                if not allow_replacement:
                    self._rejected_count += 1
                    return False, "Mempool capacity reached."

                lowest = min(
                    self._entries.values(),
                    key=lambda entry: (
                        entry.fee,
                        -entry.received_at,
                        entry.transaction_hash,
                    ),
                )

                if transaction.fee <= lowest.fee:
                    self._rejected_count += 1
                    return False, (
                        "Mempool capacity reached and "
                        "transaction fee is not high enough."
                    )

                self._remove_hash_locked(
                    lowest.transaction_hash,
                    count_removed=False,
                )

                self._replaced_count += 1

            entry = MempoolEntry(
                transaction=transaction,
                received_at=received_at,
            )

            self._entries[tx_hash] = entry

            self._sender_nonces.setdefault(
                transaction.sender,
                {},
            )[int(transaction.nonce)] = tx_hash

            self._seen_hashes.add(tx_hash)

            self._accepted_count += 1

            return True, "Transaction accepted."

    def add_or_raise(
        self,
        transaction: Transaction,
        received_at: float | None = None,
    ) -> MempoolEntry:
        added, reason = self.add(
            transaction,
            received_at=received_at,
        )

        if not added:
            raise TransactionRejected(reason)

        return self.get_entry(
            transaction.transaction_hash()
        )

    # ------------------------------------------------------------------
    # Removal
    # ------------------------------------------------------------------

    def _remove_hash_locked(
        self,
        transaction_hash: str,
        count_removed: bool = True,
    ) -> Transaction | None:
        entry = self._entries.pop(
            transaction_hash,
            None,
        )

        if entry is None:
            return None

        sender_nonces = self._sender_nonces.get(
            entry.sender
        )

        if sender_nonces is not None:
            sender_nonces.pop(
                entry.nonce,
                None,
            )

            if not sender_nonces:
                self._sender_nonces.pop(
                    entry.sender,
                    None,
                )

        if count_removed:
            self._removed_count += 1

        return entry.transaction

    def remove(
        self,
        transaction_hash: str,
    ) -> Transaction | None:
        with self._lock:
            return self._remove_hash_locked(
                transaction_hash,
                count_removed=True,
            )

    def remove_confirmed(
        self,
        transactions: Iterable[Transaction],
    ) -> int:
        """
        Remove transactions included in a confirmed block and
        permanently protect their hashes from replay.
        """
        removed = 0

        with self._lock:
            for transaction in transactions:
                tx_hash = transaction.transaction_hash()

                self._confirmed_hashes.add(tx_hash)
                self._seen_hashes.add(tx_hash)

                if (
                    self._remove_hash_locked(
                        tx_hash,
                        count_removed=True,
                    )
                    is not None
                ):
                    removed += 1

                current = self._confirmed_nonces.get(
                    transaction.sender,
                    0,
                )

                if transaction.nonce > current:
                    self._confirmed_nonces[
                        transaction.sender
                    ] = int(transaction.nonce)

            # Remove all now-stale sender transactions.
            for sender, confirmed_nonce in list(
                self._confirmed_nonces.items()
            ):
                stale = [
                    tx_hash
                    for tx_hash, entry
                    in self._entries.items()
                    if entry.sender == sender
                    and entry.nonce <= confirmed_nonce
                ]

                for tx_hash in stale:
                    if (
                        self._remove_hash_locked(
                            tx_hash,
                            count_removed=True,
                        )
                        is not None
                    ):
                        removed += 1

        return removed

    def mark_confirmed(
        self,
        transaction: Transaction,
    ) -> bool:
        return (
            self.remove_confirmed([transaction]) > 0
        )

    def clear(self) -> None:
        """
        Remove pending transactions only.

        Confirmed nonce/replay state is preserved.
        """
        with self._lock:
            count = len(self._entries)

            self._entries.clear()
            self._sender_nonces.clear()

            self._removed_count += count

    # ------------------------------------------------------------------
    # Fee ordering
    # ------------------------------------------------------------------

    def fee_ordered_entries(self) -> list[MempoolEntry]:
        with self._lock:
            return sorted(
                self._entries.values(),
                key=lambda entry: (
                    -entry.fee,
                    entry.received_at,
                    entry.transaction_hash,
                ),
            )

    def fee_ordered_transactions(self) -> list[Transaction]:
        return [
            entry.transaction
            for entry in self.fee_ordered_entries()
        ]

    # ------------------------------------------------------------------
    # Executable transactions
    # ------------------------------------------------------------------

    def _initial_executable_nonce(
        self,
        sender: str,
    ) -> int:
        return self._confirmed_nonces.get(
            sender,
            0,
        ) + 1

    def executable_transactions(self) -> list[Transaction]:
        """
        Return transactions that can currently execute without
        nonce gaps, ordered by fee.
        """
        with self._lock:
            expected = {
                sender: self._initial_executable_nonce(sender)
                for sender in self._sender_nonces
            }

            result: list[Transaction] = []

            while True:
                candidates: list[MempoolEntry] = []

                for entry in self._entries.values():
                    sender = entry.sender

                    if entry.nonce == expected.get(
                        sender,
                        self._initial_executable_nonce(sender),
                    ):
                        candidates.append(entry)

                if not candidates:
                    break

                candidates.sort(
                    key=lambda entry: (
                        -entry.fee,
                        entry.received_at,
                        entry.transaction_hash,
                    )
                )

                selected = candidates[0]
                result.append(selected.transaction)

                expected[selected.sender] = (
                    selected.nonce + 1
                )

            return result

    def select_for_block(
        self,
        max_transactions: int | None = None,
    ) -> list[Transaction]:
        """
        Select executable transactions for a block.

        Highest fee is preferred, while nonce ordering is enforced
        per sender.
        """
        with self._lock:
            if max_transactions is None:
                limit = len(self._entries)
            else:
                if max_transactions < 0:
                    raise ValueError(
                        "max_transactions cannot be negative."
                    )

                limit = int(max_transactions)

            expected = {
                sender: self._initial_executable_nonce(sender)
                for sender in self._sender_nonces
            }

            selected: list[Transaction] = []
            selected_hashes: set[str] = set()

            while len(selected) < limit:
                candidates: list[MempoolEntry] = []

                for entry in self._entries.values():
                    if entry.transaction_hash in selected_hashes:
                        continue

                    required_nonce = expected.get(
                        entry.sender,
                        self._initial_executable_nonce(
                            entry.sender
                        ),
                    )

                    if entry.nonce == required_nonce:
                        candidates.append(entry)

                if not candidates:
                    break

                candidates.sort(
                    key=lambda entry: (
                        -entry.fee,
                        entry.received_at,
                        entry.transaction_hash,
                    )
                )

                chosen = candidates[0]

                selected.append(chosen.transaction)
                selected_hashes.add(
                    chosen.transaction_hash
                )

                expected[chosen.sender] = (
                    chosen.nonce + 1
                )

            return selected

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return {
                "version": MEMPOOL_STORE_VERSION,
                "config": {
                    "max_transactions": self.max_transactions,
                    "max_transactions_per_sender": (
                        self.max_transactions_per_sender
                    ),
                    "min_fee": self.min_fee,
                },
                "transactions": [
                    entry.to_dict()
                    for entry in self._entries.values()
                ],
                "confirmed_nonces": dict(
                    self._confirmed_nonces
                ),
                "seen_hashes": sorted(
                    self._seen_hashes
                ),
                "confirmed_hashes": sorted(
                    self._confirmed_hashes
                ),
                "counters": {
                    "accepted": self._accepted_count,
                    "rejected": self._rejected_count,
                    "removed": self._removed_count,
                    "replaced": self._replaced_count,
                },
            }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "Mempool":
        if not isinstance(data, dict):
            raise ValueError(
                "Mempool data must be a dictionary."
            )

        config = data.get("config", {})

        pool = cls(
            max_transactions=int(
                config.get(
                    "max_transactions",
                    DEFAULT_MAX_TRANSACTIONS,
                )
            ),
            max_transactions_per_sender=int(
                config.get(
                    "max_transactions_per_sender",
                    DEFAULT_MAX_TRANSACTIONS_PER_SENDER,
                )
            ),
            min_fee=float(
                config.get(
                    "min_fee",
                    MIN_MEMPOOL_FEE,
                )
            ),
        )

        with pool._lock:
            for sender, nonce in data.get(
                "confirmed_nonces",
                {},
            ).items():
                pool._confirmed_nonces[
                    str(sender)
                ] = int(nonce)

            for tx_hash in data.get(
                "confirmed_hashes",
                [],
            ):
                pool._confirmed_hashes.add(
                    str(tx_hash).lower()
                )

            for tx_hash in data.get(
                "seen_hashes",
                [],
            ):
                pool._seen_hashes.add(
                    str(tx_hash).lower()
                )

            # Rebuild active transactions without replaying
            # acceptance counters.
            for raw_entry in data.get(
                "transactions",
                [],
            ):
                entry = MempoolEntry.from_dict(
                    raw_entry
                )

                tx_hash = entry.transaction_hash

                if tx_hash in pool._confirmed_hashes:
                    raise ValueError(
                        "Persisted transaction is already "
                        "confirmed/replay protected."
                    )

                if tx_hash in pool._entries:
                    raise ValueError(
                        "Duplicate transaction in persisted mempool."
                    )

                sender_nonces = pool._sender_nonces.setdefault(
                    entry.sender,
                    {},
                )

                if entry.nonce in sender_nonces:
                    raise ValueError(
                        "Persisted sender nonce conflict."
                    )

                if len(pool._entries) >= pool.max_transactions:
                    raise ValueError(
                        "Persisted mempool exceeds capacity."
                    )

                if (
                    len(sender_nonces)
                    >= pool.max_transactions_per_sender
                ):
                    raise ValueError(
                        "Persisted sender exceeds capacity."
                    )

                confirmed_nonce = pool._confirmed_nonces.get(
                    entry.sender,
                    0,
                )

                if entry.nonce <= confirmed_nonce:
                    raise ValueError(
                        "Persisted transaction has stale nonce."
                    )

                pool._entries[tx_hash] = entry
                sender_nonces[entry.nonce] = tx_hash
                pool._seen_hashes.add(tx_hash)

            counters = data.get("counters", {})

            pool._accepted_count = int(
                counters.get("accepted", 0)
            )
            pool._rejected_count = int(
                counters.get("rejected", 0)
            )
            pool._removed_count = int(
                counters.get("removed", 0)
            )
            pool._replaced_count = int(
                counters.get("replaced", 0)
            )

        return pool

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def stats(self) -> dict[str, Any]:
        with self._lock:
            total_fees = sum(
                entry.fee
                for entry in self._entries.values()
            )

            senders = len(
                self._sender_nonces
            )

            return {
                "size": len(self._entries),
                "capacity": self.max_transactions,
                "remaining_capacity": max(
                    0,
                    self.max_transactions
                    - len(self._entries),
                ),
                "senders": senders,
                "confirmed_nonce_senders": len(
                    self._confirmed_nonces
                ),
                "seen_hashes": len(
                    self._seen_hashes
                ),
                "confirmed_hashes": len(
                    self._confirmed_hashes
                ),
                "total_pending_fees": total_fees,
                "min_fee": self.min_fee,
                "accepted": self._accepted_count,
                "rejected": self._rejected_count,
                "removed": self._removed_count,
                "replaced": self._replaced_count,
            }


# ======================================================================
# 16F - PERSISTENT MEMPOOL STORE
# ======================================================================


class MempoolStore:
    """
    SQLite-backed persistent mempool.

    The store preserves:
    - pending transactions
    - received timestamps
    - confirmed nonces
    - replay-protected hashes
    - mempool configuration
    - counters
    """

    def __init__(self, db_path: str | os.PathLike[str]):
        self.db_path = Path(db_path)

    def _connect(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        connection = sqlite3.connect(
            str(self.db_path)
        )

        connection.execute("PRAGMA foreign_keys = ON")

        return connection

    def _create_schema(
        self,
        connection: sqlite3.Connection,
    ) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mempool_meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mempool_transactions (
                tx_hash TEXT PRIMARY KEY,
                transaction_json TEXT NOT NULL,
                received_at REAL NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mempool_confirmed_nonces (
                sender TEXT PRIMARY KEY,
                nonce INTEGER NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mempool_seen_hashes (
                tx_hash TEXT PRIMARY KEY
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS mempool_confirmed_hashes (
                tx_hash TEXT PRIMARY KEY
            )
            """
        )

        connection.commit()

    def save(self, pool: Mempool) -> None:
        if not isinstance(pool, Mempool):
            raise TypeError(
                "pool must be a Mempool."
            )

        payload = pool.to_dict()

        connection = self._connect()

        try:
            self._create_schema(connection)

            with connection:
                connection.execute(
                    "DELETE FROM mempool_meta"
                )
                connection.execute(
                    "DELETE FROM mempool_transactions"
                )
                connection.execute(
                    "DELETE FROM mempool_confirmed_nonces"
                )
                connection.execute(
                    "DELETE FROM mempool_seen_hashes"
                )
                connection.execute(
                    "DELETE FROM mempool_confirmed_hashes"
                )

                meta = {
                    "version": payload["version"],
                    "config": payload["config"],
                    "counters": payload["counters"],
                }

                connection.execute(
                    """
                    INSERT INTO mempool_meta
                    (key, value)
                    VALUES (?, ?)
                    """,
                    (
                        "state",
                        _canonical_json(meta),
                    ),
                )

                for entry in payload["transactions"]:
                    transaction = entry["transaction"]

                    tx_hash = transaction[
                        "transaction_hash"
                    ]

                    connection.execute(
                        """
                        INSERT INTO mempool_transactions
                        (
                            tx_hash,
                            transaction_json,
                            received_at
                        )
                        VALUES (?, ?, ?)
                        """,
                        (
                            tx_hash,
                            _canonical_json(
                                transaction
                            ),
                            float(
                                entry["received_at"]
                            ),
                        ),
                    )

                for sender, nonce in payload[
                    "confirmed_nonces"
                ].items():
                    connection.execute(
                        """
                        INSERT INTO mempool_confirmed_nonces
                        (sender, nonce)
                        VALUES (?, ?)
                        """,
                        (
                            sender,
                            int(nonce),
                        ),
                    )

                for tx_hash in payload[
                    "seen_hashes"
                ]:
                    connection.execute(
                        """
                        INSERT INTO mempool_seen_hashes
                        (tx_hash)
                        VALUES (?)
                        """,
                        (tx_hash,),
                    )

                for tx_hash in payload[
                    "confirmed_hashes"
                ]:
                    connection.execute(
                        """
                        INSERT INTO mempool_confirmed_hashes
                        (tx_hash)
                        VALUES (?)
                        """,
                        (tx_hash,),
                    )

        except Exception as exc:
            raise MempoolPersistenceError(
                f"Failed to save mempool: {exc}"
            ) from exc

        finally:
            connection.close()

    def exists(self) -> bool:
        return self.db_path.exists()

    def load(self) -> Mempool:
        if not self.exists():
            raise MempoolPersistenceError(
                "Mempool database does not exist."
            )

        connection = self._connect()

        try:
            self._create_schema(connection)

            meta_row = connection.execute(
                """
                SELECT value
                FROM mempool_meta
                WHERE key = 'state'
                """
            ).fetchone()

            if meta_row is None:
                raise MempoolPersistenceError(
                    "Mempool metadata is missing."
                )

            meta = json.loads(meta_row[0])

            config = meta["config"]

            transactions = []

            rows = connection.execute(
                """
                SELECT
                    tx_hash,
                    transaction_json,
                    received_at
                FROM mempool_transactions
                ORDER BY received_at ASC, tx_hash ASC
                """
            ).fetchall()

            for tx_hash, transaction_json, received_at in rows:
                transaction = json.loads(
                    transaction_json
                )

                calculated_hash = (
                    Transaction.from_dict(
                        transaction
                    ).transaction_hash()
                )

                if calculated_hash != tx_hash:
                    raise MempoolPersistenceError(
                        "Persisted transaction hash mismatch."
                    )

                transactions.append(
                    {
                        "transaction": transaction,
                        "received_at": received_at,
                    }
                )

            confirmed_nonces = {
                sender: nonce
                for sender, nonce in connection.execute(
                    """
                    SELECT sender, nonce
                    FROM mempool_confirmed_nonces
                    """
                ).fetchall()
            }

            seen_hashes = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT tx_hash
                    FROM mempool_seen_hashes
                    """
                ).fetchall()
            ]

            confirmed_hashes = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT tx_hash
                    FROM mempool_confirmed_hashes
                    """
                ).fetchall()
            ]

            counters = meta.get(
                "counters",
                {},
            )

            data = {
                "version": int(
                    meta.get(
                        "version",
                        MEMPOOL_STORE_VERSION,
                    )
                ),
                "config": config,
                "transactions": transactions,
                "confirmed_nonces": confirmed_nonces,
                "seen_hashes": seen_hashes,
                "confirmed_hashes": confirmed_hashes,
                "counters": counters,
            }

            return Mempool.from_dict(data)

        except MempoolPersistenceError:
            raise

        except Exception as exc:
            raise MempoolPersistenceError(
                f"Failed to load mempool: {exc}"
            ) from exc

        finally:
            connection.close()

    def verify(self) -> tuple[bool, str]:
        if not self.exists():
            return False, "Mempool database does not exist."

        try:
            pool = self.load()

            valid, reason = self._verify_pool(pool)

            if not valid:
                return False, reason

            return True, "Mempool persistence is valid."

        except Exception as exc:
            return False, str(exc)

    @staticmethod
    def _verify_pool(
        pool: Mempool,
    ) -> tuple[bool, str]:
        hashes = set()

        for entry in pool.get_entries():
            tx_hash = entry.transaction_hash

            if tx_hash in hashes:
                return False, (
                    "Duplicate transaction hash."
                )

            hashes.add(tx_hash)

            calculated = (
                entry.transaction.transaction_hash()
            )

            if calculated != tx_hash:
                return False, (
                    "Transaction hash verification failed."
                )

        return True, "Valid."

    def replace(self, pool: Mempool) -> None:
        self.save(pool)

    def clear(self) -> None:
        connection = self._connect()

        try:
            self._create_schema(connection)

            with connection:
                connection.execute(
                    "DELETE FROM mempool_meta"
                )
                connection.execute(
                    "DELETE FROM mempool_transactions"
                )
                connection.execute(
                    "DELETE FROM mempool_confirmed_nonces"
                )
                connection.execute(
                    "DELETE FROM mempool_seen_hashes"
                )
                connection.execute(
                    "DELETE FROM mempool_confirmed_hashes"
                )

        finally:
            connection.close()


# ======================================================================
# 16G - P2P TRANSACTION PROPAGATION
# ======================================================================


class MempoolPropagator:
    """
    Bridges the mempool with the existing NEXCHAIN TCP network.

    It intentionally uses the existing NetworkNode/TCPTransport
    interface instead of creating a second networking implementation.
    """

    def __init__(
        self,
        mempool: Mempool,
        transport: Any,
    ):
        if not isinstance(mempool, Mempool):
            raise TypeError(
                "mempool must be a Mempool."
            )

        self.mempool = mempool
        self.transport = transport

        self._seen_message_ids: set[str] = set()
        self._lock = threading.RLock()

        self.propagated_count = 0
        self.received_count = 0
        self.accepted_count = 0
        self.rejected_count = 0
        self.duplicate_message_count = 0

    # ------------------------------------------------------------------
    # Message creation
    # ------------------------------------------------------------------

    def _create_message(
        self,
        transaction: Transaction,
    ) -> Any:
        payload = {
            "transaction": transaction.to_dict(),
        }

        node = getattr(
            self.transport,
            "node",
            None,
        )

        if node is not None:
            creator = getattr(
                node,
                "create_message",
                None,
            )

            if callable(creator):
                return creator(
                    P2P_MESSAGE_TYPE,
                    payload,
                )

        # Fallback useful for lightweight test transports.
        transaction_hash = (
            transaction.transaction_hash()
        )

        return {
            "message_type": P2P_MESSAGE_TYPE,
            "payload": payload,
            "message_id": _sha256_text(
                _canonical_json(payload)
            ),
            "transaction_hash": transaction_hash,
        }

    # ------------------------------------------------------------------
    # Connected peers
    # ------------------------------------------------------------------

    def _connected_peer_ids(self) -> list[str]:
        value = getattr(
            self.transport,
            "connected_node_ids",
            [],
        )

        try:
            value = value() if callable(value) else value
        except TypeError:
            value = []

        if value is None:
            return []

        return list(value)

    # ------------------------------------------------------------------
    # Propagation
    # ------------------------------------------------------------------

    def propagate(
        self,
        transaction: Transaction,
        exclude_peer_id: str | None = None,
    ) -> int:
        message = self._create_message(
            transaction
        )

        sent = 0

        for peer_id in self._connected_peer_ids():
            if peer_id == exclude_peer_id:
                continue

            try:
                result = self.transport.send(
                    peer_id,
                    message,
                )

                # A transport may return False on failure.
                if result is False:
                    continue

                sent += 1

            except Exception:
                continue

        with self._lock:
            self.propagated_count += sent

        return sent

    def broadcast_transaction(
        self,
        transaction: Transaction,
        exclude_peer_id: str | None = None,
    ) -> int:
        return self.propagate(
            transaction,
            exclude_peer_id=exclude_peer_id,
        )

    # ------------------------------------------------------------------
    # Incoming message parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _message_fields(
        message: Any,
    ) -> tuple[str | None, dict[str, Any]]:
        if isinstance(message, dict):
            message_type = message.get(
                "message_type"
            )
            payload = message.get(
                "payload",
                {},
            )

            if not isinstance(payload, dict):
                payload = {}

            return message_type, payload

        message_type = getattr(
            message,
            "message_type",
            None,
        )

        payload = getattr(
            message,
            "payload",
            {})

        if not isinstance(payload, dict):
            payload = {}

        return message_type, payload

    @staticmethod
    def _message_id(
        message: Any,
        payload: dict[str, Any],
    ) -> str:
        if isinstance(message, dict):
            value = message.get(
                "message_id"
            )
        else:
            value = getattr(
                message,
                "message_id",
                None,
            )

        if value:
            return str(value)

        return _sha256_text(
            _canonical_json(payload)
        )

    # ------------------------------------------------------------------
    # Incoming transaction
    # ------------------------------------------------------------------

    def receive(
        self,
        message: Any,
        from_peer_id: str | None = None,
    ) -> tuple[bool, str]:
        message_type, payload = (
            self._message_fields(message)
        )

        if message_type != P2P_MESSAGE_TYPE:
            return False, (
                "Unsupported network message type."
            )

        message_id = self._message_id(
            message,
            payload,
        )

        with self._lock:
            self.received_count += 1

            if message_id in self._seen_message_ids:
                self.duplicate_message_count += 1
                return False, (
                    "Duplicate network message."
                )

            self._seen_message_ids.add(
                message_id
            )

        raw_transaction = payload.get(
            "transaction"
        )

        if not isinstance(
            raw_transaction,
            dict,
        ):
            with self._lock:
                self.rejected_count += 1

            return False, (
                "Transaction payload is missing."
            )

        try:
            transaction = Transaction.from_dict(
                raw_transaction
            )

            added, reason = self.mempool.add(
                transaction
            )

        except Exception as exc:
            with self._lock:
                self.rejected_count += 1

            return False, (
                f"Transaction decoding failed: {exc}"
            )

        if not added:
            with self._lock:
                self.rejected_count += 1

            return False, reason

        with self._lock:
            self.accepted_count += 1

        # Relay only newly accepted transactions.
        self.propagate(
            transaction,
            exclude_peer_id=from_peer_id,
        )

        return True, "Transaction accepted and propagated."

    def receive_transaction_message(
        self,
        message: Any,
        from_peer_id: str | None = None,
    ) -> tuple[bool, str]:
        return self.receive(
            message,
            from_peer_id=from_peer_id,
        )

    def stats(self) -> dict[str, Any]:
        with self._lock:
            return {
                "propagated": self.propagated_count,
                "received": self.received_count,
                "accepted": self.accepted_count,
                "rejected": self.rejected_count,
                "duplicate_messages": (
                    self.duplicate_message_count
                ),
                "seen_message_ids": len(
                    self._seen_message_ids
                ),
            }


# ======================================================================
# 16H - FULL INTEGRATION TEST
# ======================================================================


def _make_test_transaction(
    wallet: Any,
    recipient: str,
    amount: float,
    fee: float,
    nonce: int,
    timestamp: float,
) -> Transaction:
    transaction = Transaction(
        sender=wallet.address(),
        recipient=recipient,
        amount=amount,
        fee=fee,
        nonce=nonce,
        timestamp=timestamp,
        public_key=wallet.public_key_bytes(),
    )

    transaction.sign(wallet)

    return transaction


def self_test() -> None:
    from crypto.crypto_engine import Wallet

    print("=" * 70)
    print("NEXCHAIN MEMPOOL 16A-16H TEST")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Test wallets
    # ------------------------------------------------------------------

    sender_a = Wallet.generate()
    sender_b = Wallet.generate()
    sender_c = Wallet.generate()

    recipient_a = Wallet.generate().address()
    recipient_b = Wallet.generate().address()
    recipient_c = Wallet.generate().address()

    # ------------------------------------------------------------------
    # 16A - Initialization
    # ------------------------------------------------------------------

    pool = Mempool(
        max_transactions=10,
        max_transactions_per_sender=5,
        min_fee=MIN_MEMPOOL_FEE,
    )

    assert pool.size == 0
    assert pool.capacity == 10
    assert pool.remaining_capacity == 10

    print("[PASS] 16A Mempool initialization")

    # ------------------------------------------------------------------
    # 16B - Admission
    # ------------------------------------------------------------------

    tx1 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=10,
        fee=0.001,
        nonce=1,
        timestamp=1001,
    )

    added, reason = pool.add(tx1)

    assert added is True, reason
    assert pool.contains(
        tx1.transaction_hash()
    )

    print("[PASS] 16B Transaction admission")

    # ------------------------------------------------------------------
    # 16B - Duplicate protection
    # ------------------------------------------------------------------

    duplicate_added, _ = pool.add(tx1)

    assert duplicate_added is False

    print(
        "[PASS] 16B Duplicate transaction protection"
    )

    # ------------------------------------------------------------------
    # 16B - Fee validation
    # ------------------------------------------------------------------

    low_fee_tx = _make_test_transaction(
        sender_b,
        recipient_b,
        amount=5,
        fee=0.0,
        nonce=1,
        timestamp=1002,
    )

    low_added, _ = pool.add(low_fee_tx)

    assert low_added is False

    print("[PASS] 16B Fee validation")

    # ------------------------------------------------------------------
    # 16C - Fee ordering
    # ------------------------------------------------------------------

    tx2 = _make_test_transaction(
        sender_b,
        recipient_b,
        amount=10,
        fee=0.005,
        nonce=1,
        timestamp=1003,
    )

    tx3 = _make_test_transaction(
        sender_c,
        recipient_c,
        amount=10,
        fee=0.002,
        nonce=1,
        timestamp=1004,
    )

    assert pool.add(tx2)[0] is True
    assert pool.add(tx3)[0] is True

    ordered = pool.fee_ordered_transactions()

    assert ordered[0].transaction_hash() == (
        tx2.transaction_hash()
    )

    assert ordered[1].transaction_hash() == (
        tx3.transaction_hash()
    )

    print("[PASS] 16C Fee ordering")

    # ------------------------------------------------------------------
    # 16C - Sequential block selection
    # ------------------------------------------------------------------

    tx4 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=5,
        fee=0.010,
        nonce=2,
        timestamp=1005,
    )

    assert pool.add(tx4)[0] is True

    selected = pool.select_for_block(
        max_transactions=4
    )

    assert len(selected) == 4

    # Sender A nonce 1 must appear before sender A nonce 2.
    positions = {
        tx.transaction_hash(): index
        for index, tx in enumerate(selected)
    }

    assert positions[
        tx1.transaction_hash()
    ] < positions[
        tx4.transaction_hash()
    ]

    print(
        "[PASS] 16C Sequential block selection"
    )

    # ------------------------------------------------------------------
    # 16D - Nonce management
    # ------------------------------------------------------------------

    assert pool.next_expected_nonce(sender_a.address()) == 0

    assert pool.is_nonce_available(
        sender_a.address(),
        3,
    )

    assert not pool.is_nonce_available(
        sender_a.address(),
        1,
    )

    print("[PASS] 16D Nonce management")

    # ------------------------------------------------------------------
    # 16D - Nonce gap protection
    # ------------------------------------------------------------------

    gap_pool = Mempool()

    gap_tx2 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=5,
        fee=0.020,
        nonce=3,
        timestamp=1006,
    )

    assert gap_pool.add(gap_tx2)[0] is True

    gap_selected = gap_pool.select_for_block()

    assert len(gap_selected) == 0

    gap_tx1 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=5,
        fee=0.001,
        nonce=1,
        timestamp=1007,
    )

    assert gap_pool.add(gap_tx1)[0] is True

    gap_selected = gap_pool.select_for_block()

    assert len(gap_selected) == 1
    assert gap_selected[0].nonce == 1

    print("[PASS] 16D Nonce gap protection")

    # ------------------------------------------------------------------
    # 16E - Replay protection
    # ------------------------------------------------------------------

    replay_hash = _sha256_text(
        "nexchain-replay-test"
    )

    assert pool.mark_seen(
        replay_hash
    ) is True

    assert pool.mark_seen(
        replay_hash
    ) is False

    assert pool.has_seen(
        replay_hash
    ) is True

    print("[PASS] 16E Replay protection")

    # ------------------------------------------------------------------
    # 16E - Confirmed replay protection
    # ------------------------------------------------------------------

    confirmed_pool = Mempool()

    confirmed_tx = _make_test_transaction(
        sender_b,
        recipient_b,
        amount=7,
        fee=0.003,
        nonce=1,
        timestamp=1010,
    )

    assert confirmed_pool.add(
        confirmed_tx
    )[0] is True

    removed = confirmed_pool.remove_confirmed(
        [confirmed_tx]
    )

    assert removed == 1

    assert confirmed_pool.is_confirmed_hash(
        confirmed_tx.transaction_hash()
    )

    replay_added, _ = confirmed_pool.add(
        confirmed_tx
    )

    assert replay_added is False

    print(
        "[PASS] 16E Confirmed transaction replay protection"
    )

    # ------------------------------------------------------------------
    # 16F - Persistence
    # ------------------------------------------------------------------

    persistence_pool = Mempool(
        max_transactions=50,
        max_transactions_per_sender=10,
    )

    persist_tx1 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=20,
        fee=0.004,
        nonce=1,
        timestamp=1020,
    )

    persist_tx2 = _make_test_transaction(
        sender_b,
        recipient_b,
        amount=15,
        fee=0.006,
        nonce=1,
        timestamp=1021,
    )

    assert persistence_pool.add(
        persist_tx1
    )[0] is True

    assert persistence_pool.add(
        persist_tx2
    )[0] is True

    persistence_pool.set_confirmed_nonce(
        sender_c.address(),
        4,
    )

    temp_directory = Path(
        tempfile.mkdtemp(
            prefix="nexchain_mempool_"
        )
    )

    database_path = (
        temp_directory / "mempool.db"
    )

    try:
        store = MempoolStore(
            database_path
        )

        store.save(
            persistence_pool
        )

        assert store.exists()

        restored = store.load()

        assert restored.size == 2

        assert set(
            restored.transaction_hashes()
        ) == set(
            persistence_pool.transaction_hashes()
        )

        assert restored.confirmed_nonce(
            sender_c.address()
        ) == 4

        print(
            "[PASS] 16F Mempool persistence"
        )

        verified, verify_reason = (
            store.verify()
        )

        assert verified, verify_reason

        print(
            "[PASS] 16F Persistence verification"
        )

    finally:
        # SQLite connections are already closed by this point.
        for suffix in (
            "",
            "-wal",
            "-shm",
        ):
            path = Path(
                str(database_path) + suffix
            )

            try:
                if path.exists():
                    path.unlink()
            except PermissionError:
                pass

        try:
            temp_directory.rmdir()
        except OSError:
            pass

    # ------------------------------------------------------------------
    # 16G - Fake transport
    # ------------------------------------------------------------------

    class FakeNode:
        def create_message(
            self,
            message_type: str,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            return {
                "message_type": message_type,
                "payload": payload,
                "message_id": _sha256_text(
                    _canonical_json(payload)
                ),
            }

    class FakeTransport:
        def __init__(self):
            self.node = FakeNode()
            self.peers = [
                "peer-a",
                "peer-b",
                "peer-c",
            ]
            self.sent: list[
                tuple[str, Any]
            ] = []

        @property
        def connected_node_ids(self):
            return list(self.peers)

        def send(
            self,
            peer_id: str,
            message: Any,
        ):
            self.sent.append(
                (
                    peer_id,
                    message,
                )
            )

            return True

    propagation_pool = Mempool()

    fake_transport = FakeTransport()

    propagator = MempoolPropagator(
        propagation_pool,
        fake_transport,
    )

    propagation_tx = _make_test_transaction(
        sender_c,
        recipient_c,
        amount=11,
        fee=0.009,
        nonce=1,
        timestamp=1030,
    )

    sent_count = propagator.propagate(
        propagation_tx
    )

    assert sent_count == 3
    assert len(
        fake_transport.sent
    ) == 3

    print(
        "[PASS] 16G P2P transaction propagation"
    )

    # ------------------------------------------------------------------
    # 16G - Incoming transaction + relay
    # ------------------------------------------------------------------

    receiver_pool = Mempool()

    receiver_transport = FakeTransport()

    receiver_propagator = MempoolPropagator(
        receiver_pool,
        receiver_transport,
    )

    incoming_message = fake_transport.sent[0][1]

    received, receive_reason = (
        receiver_propagator.receive(
            incoming_message,
            from_peer_id="peer-a",
        )
    )

    assert received, receive_reason

    assert receiver_pool.contains(
        propagation_tx.transaction_hash()
    )

    # Must relay to peer-b and peer-c,
    # but never back to peer-a.
    relay_peers = [
        peer_id
        for peer_id, _message
        in receiver_transport.sent
    ]

    assert "peer-a" not in relay_peers
    assert "peer-b" in relay_peers
    assert "peer-c" in relay_peers

    print(
        "[PASS] 16G Incoming transaction relay"
    )

    # ------------------------------------------------------------------
    # 16G - Duplicate propagation protection
    # ------------------------------------------------------------------

    sent_before = len(
        receiver_transport.sent
    )

    duplicate_received, _ = (
        receiver_propagator.receive(
            incoming_message,
            from_peer_id="peer-c",
        )
    )

    assert duplicate_received is False

    assert len(
        receiver_transport.sent
    ) == sent_before

    print(
        "[PASS] 16G Duplicate propagation protection"
    )

    # ------------------------------------------------------------------
    # 16H - Capacity replacement
    # ------------------------------------------------------------------

    capacity_pool = Mempool(
        max_transactions=2,
        max_transactions_per_sender=5,
    )

    capacity_tx1 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=1,
        fee=0.001,
        nonce=1,
        timestamp=1040,
    )

    capacity_tx2 = _make_test_transaction(
        sender_b,
        recipient_b,
        amount=1,
        fee=0.002,
        nonce=1,
        timestamp=1041,
    )

    capacity_tx3 = _make_test_transaction(
        sender_c,
        recipient_c,
        amount=1,
        fee=0.010,
        nonce=1,
        timestamp=1042,
    )

    assert capacity_pool.add(
        capacity_tx1
    )[0] is True

    assert capacity_pool.add(
        capacity_tx2
    )[0] is True

    replaced, replace_reason = (
        capacity_pool.add(
            capacity_tx3
        )
    )

    assert replaced, replace_reason

    assert not capacity_pool.contains(
        capacity_tx1.transaction_hash()
    )

    assert capacity_pool.contains(
        capacity_tx3.transaction_hash()
    )

    # ------------------------------------------------------------------
    # 16H - Sender limit
    # ------------------------------------------------------------------

    sender_limit_pool = Mempool(
        max_transactions=20,
        max_transactions_per_sender=1,
    )

    sender_limit_tx1 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=1,
        fee=0.001,
        nonce=1,
        timestamp=1050,
    )

    sender_limit_tx2 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=1,
        fee=0.002,
        nonce=2,
        timestamp=1051,
    )

    assert sender_limit_pool.add(
        sender_limit_tx1
    )[0] is True

    sender_limit_added, _ = (
        sender_limit_pool.add(
            sender_limit_tx2
        )
    )

    assert sender_limit_added is False

    # ------------------------------------------------------------------
    # 16H - Sequential multi-sender fee selection
    # ------------------------------------------------------------------

    selection_pool = Mempool(
        max_transactions=20,
        max_transactions_per_sender=10,
    )

    selection_a1 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=1,
        fee=0.001,
        nonce=1,
        timestamp=1060,
    )

    selection_a2 = _make_test_transaction(
        sender_a,
        recipient_a,
        amount=1,
        fee=0.020,
        nonce=2,
        timestamp=1061,
    )

    selection_b1 = _make_test_transaction(
        sender_b,
        recipient_b,
        amount=1,
        fee=0.010,
        nonce=1,
        timestamp=1062,
    )

    assert selection_pool.add(
        selection_a1
    )[0] is True

    assert selection_pool.add(
        selection_a2
    )[0] is True

    assert selection_pool.add(
        selection_b1
    )[0] is True

    selected = selection_pool.select_for_block()

    assert len(selected) == 3

    selection_hashes = [
        tx.transaction_hash()
        for tx in selected
    ]

    assert selection_hashes.index(
        selection_a1.transaction_hash()
    ) < selection_hashes.index(
        selection_a2.transaction_hash()
    )

    # ------------------------------------------------------------------
    # 16H - Serialization round trip
    # ------------------------------------------------------------------

    serialized = selection_pool.to_dict()

    restored_pool = Mempool.from_dict(
        serialized
    )

    assert restored_pool.size == (
        selection_pool.size
    )

    assert set(
        restored_pool.transaction_hashes()
    ) == set(
        selection_pool.transaction_hashes()
    )

    # ------------------------------------------------------------------
    # 16H - Final state
    # ------------------------------------------------------------------

    final_stats = pool.stats()

    assert final_stats["size"] > 0
    assert final_stats["accepted"] > 0
    assert final_stats["rejected"] > 0

    print(
        "[PASS] 16H Full integration"
    )

    print("=" * 70)
    print(
        "NEXCHAIN MEMPOOL 16A-16H TEST: ALL PASSED"
    )
    print("=" * 70)


# ======================================================================
# ENTRY POINT
# ======================================================================


if __name__ == "__main__":
    self_test()