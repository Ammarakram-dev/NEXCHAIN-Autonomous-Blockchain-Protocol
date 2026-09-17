"""
NEXCHAIN — Persistent State Store
=================================

Step 12
Persistent State + Blockchain Recovery

Responsibilities:
    - Persist StateEngine accounts into SQLite
    - Restore state safely
    - Verify state integrity
    - Persist state root and total supply
    - Detect corruption
    - Create snapshots
    - Perform atomic state replacement
    - Support blockchain recovery
    - Remain compatible with the existing NEXCHAIN StateEngine

Standard library only.
"""

from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from core.state import Account, StateEngine


# ============================================================================
# CONSTANTS
# ============================================================================

DEFAULT_DB_PATH = Path("data") / "nexchain_state.db"

SCHEMA_VERSION = 1

METADATA_STATE_ROOT = "state_root"
METADATA_TOTAL_SUPPLY = "total_supply"
METADATA_SCHEMA_VERSION = "schema_version"


# ============================================================================
# EXCEPTIONS
# ============================================================================

class StateStoreError(Exception):
    """Base exception for persistent state errors."""


class StateStoreCorruptionError(StateStoreError):
    """Raised when persistent state fails integrity validation."""


class StateStoreVersionError(StateStoreError):
    """Raised when the database schema is unsupported."""


# ============================================================================
# STATE STORE
# ============================================================================

class StateStore:
    """
    Persistent SQLite-backed storage for NEXCHAIN StateEngine.

    Database structure:

        metadata
            key
            value

        accounts
            address
            balance
            nonce

    Every persisted state also stores:
        - state root
        - total supply
        - schema version
    """

    def __init__(
        self,
        db_path: str | Path = DEFAULT_DB_PATH,
    ) -> None:

        self.db_path = Path(db_path)

        self.db_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self._initialize_database()

    # ========================================================================
    # CONNECTION
    # ========================================================================

    def _connect(self) -> sqlite3.Connection:
        """
        Create a configured SQLite connection.

        The schema is defensively verified/created on every connection.
        This prevents runtime failures when a SQLite database file exists
        but contains no tables.
        """

        connection = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
        )

        connection.row_factory = sqlite3.Row

        try:
            connection.execute(
                "PRAGMA foreign_keys = ON"
            )

            connection.execute(
                "PRAGMA synchronous = FULL"
            )

            # ----------------------------------------------------------------
            # DEFENSIVE SCHEMA INITIALIZATION
            # ----------------------------------------------------------------

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    address TEXT PRIMARY KEY,
                    balance REAL NOT NULL,
                    nonce INTEGER NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accounts_address
                ON accounts(address)
                """
            )

            existing_version = connection.execute(
                """
                SELECT value
                FROM metadata
                WHERE key = ?
                """,
                (METADATA_SCHEMA_VERSION,),
            ).fetchone()

            if existing_version is None:
                self._set_metadata(
                    connection,
                    METADATA_SCHEMA_VERSION,
                    SCHEMA_VERSION,
                )

            else:
                raw_version = existing_version["value"]

                try:
                    version = int(
                        json.loads(raw_version)
                    )
                except (
                    TypeError,
                    ValueError,
                    json.JSONDecodeError,
                ) as exc:
                    raise StateStoreVersionError(
                        "Invalid database schema version."
                    ) from exc

                if version != SCHEMA_VERSION:
                    raise StateStoreVersionError(
                        f"Unsupported schema version: {version}. "
                        f"Expected: {SCHEMA_VERSION}."
                    )

            connection.commit()

            return connection

        except Exception:
            connection.rollback()
            connection.close()
            raise

    # ========================================================================
    # DATABASE INITIALIZATION
    # ========================================================================

    def _initialize_database(self) -> None:
        """
        Create database schema if it does not already exist.
        """

        connection = self._connect()

        try:
            # _connect() already guarantees the schema.
            # This method remains intentionally explicit for clarity
            # and compatibility with existing StateStore behavior.

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS metadata (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS accounts (
                    address TEXT PRIMARY KEY,
                    balance REAL NOT NULL,
                    nonce INTEGER NOT NULL
                )
                """
            )

            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_accounts_address
                ON accounts(address)
                """
            )

            existing_version = self._get_metadata(
                connection,
                METADATA_SCHEMA_VERSION,
            )

            if existing_version is None:
                self._set_metadata(
                    connection,
                    METADATA_SCHEMA_VERSION,
                    SCHEMA_VERSION,
                )

            else:
                try:
                    version = int(existing_version)
                except (TypeError, ValueError) as exc:
                    raise StateStoreVersionError(
                        "Invalid database schema version."
                    ) from exc

                if version != SCHEMA_VERSION:
                    raise StateStoreVersionError(
                        f"Unsupported schema version: {version}. "
                        f"Expected: {SCHEMA_VERSION}."
                    )

            connection.commit()

        finally:
            connection.close()

    # ========================================================================
    # METADATA
    # ========================================================================

    @staticmethod
    def _get_metadata(
        connection: sqlite3.Connection,
        key: str,
    ) -> Any:

        row = connection.execute(
            """
            SELECT value
            FROM metadata
            WHERE key = ?
            """,
            (key,),
        ).fetchone()

        if row is None:
            return None

        raw_value = row["value"]

        try:
            return json.loads(raw_value)
        except json.JSONDecodeError:
            return raw_value

    @staticmethod
    def _set_metadata(
        connection: sqlite3.Connection,
        key: str,
        value: Any,
    ) -> None:

        encoded = json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
        )

        connection.execute(
            """
            INSERT INTO metadata(key, value)
            VALUES(?, ?)
            ON CONFLICT(key)
            DO UPDATE SET value = excluded.value
            """,
            (key, encoded),
        )

    # ========================================================================
    # INTERNAL STATE VALIDATION
    # ========================================================================

    @staticmethod
    def _validate_state(state: StateEngine) -> None:
        """
        Validate a StateEngine without depending on a non-existent
        verify_invariants() method.
        """

        if not isinstance(state, StateEngine):
            raise TypeError(
                "state must be a StateEngine instance."
            )

        accounts = getattr(
            state,
            "accounts",
            None,
        )

        if not isinstance(accounts, dict):
            raise StateStoreCorruptionError(
                "StateEngine accounts collection is invalid."
            )

        calculated_supply = 0.0

        for address, account in accounts.items():

            if not isinstance(address, str):
                raise StateStoreCorruptionError(
                    "Account address must be a string."
                )

            if not address.startswith("NEX"):
                raise StateStoreCorruptionError(
                    f"Invalid NEX address prefix: {address}"
                )

            if len(address) != 43:
                raise StateStoreCorruptionError(
                    f"Invalid NEX address length: {address}"
                )

            if not isinstance(account, Account):
                raise StateStoreCorruptionError(
                    f"Invalid account object: {address}"
                )

            if account.address != address:
                raise StateStoreCorruptionError(
                    f"Account address mismatch: {address}"
                )

            try:
                balance = float(account.balance)
            except (TypeError, ValueError) as exc:
                raise StateStoreCorruptionError(
                    f"Invalid balance for account: {address}"
                ) from exc

            if balance < 0:
                raise StateStoreCorruptionError(
                    f"Negative balance for account: {address}"
                )

            if not isinstance(account.nonce, int):
                raise StateStoreCorruptionError(
                    f"Invalid nonce for account: {address}"
                )

            if account.nonce < 0:
                raise StateStoreCorruptionError(
                    f"Negative nonce for account: {address}"
                )

            calculated_supply += balance

        if calculated_supply < 0:
            raise StateStoreCorruptionError(
                "Calculated supply cannot be negative."
            )

        max_supply = float(
            getattr(
                StateEngine,
                "MAX_SUPPLY",
                float("inf"),
            )
        )

        if calculated_supply > max_supply + 1e-9:
            raise StateStoreCorruptionError(
                "Maximum supply exceeded."
            )

        stored_supply = float(
            getattr(
                state,
                "total_supply",
                calculated_supply,
            )
        )

        if abs(
            calculated_supply - stored_supply
        ) > 1e-9:
            raise StateStoreCorruptionError(
                "Total supply does not match account balances."
            )

    # ========================================================================
    # STATE ROOT
    # ========================================================================

    @staticmethod
    def _calculate_state_root(
        state: StateEngine,
    ) -> str:

        root = state.state_root()

        if not isinstance(root, str):
            raise StateStoreCorruptionError(
                "State root must be a string."
            )

        if len(root) != 64:
            raise StateStoreCorruptionError(
                "State root must contain 64 hexadecimal characters."
            )

        try:
            int(root, 16)
        except ValueError as exc:
            raise StateStoreCorruptionError(
                "State root is not valid hexadecimal."
            ) from exc

        return root

    # ========================================================================
    # STATE ROW CONVERSION
    # ========================================================================

    @staticmethod
    def _state_to_rows(
        state: StateEngine,
    ) -> list[tuple[str, float, int]]:

        rows: list[tuple[str, float, int]] = []

        for address in sorted(state.accounts):

            account = state.accounts[address]

            rows.append(
                (
                    address,
                    float(account.balance),
                    int(account.nonce),
                )
            )

        return rows

    # ========================================================================
    # SAVE
    # ========================================================================

    def save(
        self,
        state: StateEngine,
    ) -> str:
        """
        Persist complete state.

        Returns:
            The persisted state root.
        """

        self._validate_state(state)

        state_root = self._calculate_state_root(state)

        rows = self._state_to_rows(state)

        total_supply = float(
            state.total_supply
        )

        connection = self._connect()

        try:
            connection.execute(
                "BEGIN IMMEDIATE"
            )

            connection.execute(
                "DELETE FROM accounts"
            )

            if rows:
                connection.executemany(
                    """
                    INSERT INTO accounts(
                        address,
                        balance,
                        nonce
                    )
                    VALUES(?, ?, ?)
                    """,
                    rows,
                )

            self._set_metadata(
                connection,
                METADATA_STATE_ROOT,
                state_root,
            )

            self._set_metadata(
                connection,
                METADATA_TOTAL_SUPPLY,
                total_supply,
            )

            self._set_metadata(
                connection,
                METADATA_SCHEMA_VERSION,
                SCHEMA_VERSION,
            )

            connection.commit()

            return state_root

        except Exception:
            connection.rollback()
            raise

        finally:
            connection.close()

    # ========================================================================
    # LOAD
    # ========================================================================

    def load(self) -> StateEngine:
        """
        Load and verify complete state from SQLite.
        """

        if not self.exists():
            raise StateStoreError(
                f"State database does not exist: {self.db_path}"
            )

        connection = self._connect()

        try:

            version = self._get_metadata(
                connection,
                METADATA_SCHEMA_VERSION,
            )

            if version is None:
                raise StateStoreVersionError(
                    "Database schema version is missing."
                )

            if int(version) != SCHEMA_VERSION:
                raise StateStoreVersionError(
                    f"Unsupported schema version: {version}"
                )

            state = StateEngine()

            rows = connection.execute(
                """
                SELECT
                    address,
                    balance,
                    nonce
                FROM accounts
                ORDER BY address ASC
                """
            ).fetchall()

            for row in rows:

                address = str(
                    row["address"]
                )

                balance = float(
                    row["balance"]
                )

                nonce = int(
                    row["nonce"]
                )

                if not address.startswith("NEX"):
                    raise StateStoreCorruptionError(
                        f"Invalid persisted address: {address}"
                    )

                if len(address) != 43:
                    raise StateStoreCorruptionError(
                        f"Invalid persisted address length: {address}"
                    )

                if balance < 0:
                    raise StateStoreCorruptionError(
                        f"Negative persisted balance: {address}"
                    )

                if nonce < 0:
                    raise StateStoreCorruptionError(
                        f"Negative persisted nonce: {address}"
                    )

                state.accounts[address] = Account(
                    address=address,
                    balance=balance,
                    nonce=nonce,
                )

            calculated_supply = sum(
                float(account.balance)
                for account in state.accounts.values()
            )

            stored_supply = self._get_metadata(
                connection,
                METADATA_TOTAL_SUPPLY,
            )

            if stored_supply is None:
                raise StateStoreCorruptionError(
                    "Persisted total supply is missing."
                )

            stored_supply = float(
                stored_supply
            )

            if abs(
                calculated_supply - stored_supply
            ) > 1e-9:
                raise StateStoreCorruptionError(
                    "Persisted total supply does not match "
                    "persisted account balances."
                )

            state.total_supply = calculated_supply

            self._validate_state(state)

            calculated_root = self._calculate_state_root(
                state
            )

            stored_root = self._get_metadata(
                connection,
                METADATA_STATE_ROOT,
            )

            if stored_root is None:
                raise StateStoreCorruptionError(
                    "Persisted state root is missing."
                )

            stored_root = str(
                stored_root
            )

            if calculated_root != stored_root:
                raise StateStoreCorruptionError(
                    "State root mismatch. "
                    f"Stored={stored_root}, "
                    f"Calculated={calculated_root}"
                )

            return state

        finally:
            connection.close()

    # ========================================================================
    # EXISTENCE
    # ========================================================================

    def exists(self) -> bool:
        """Check whether the database exists."""

        return self.db_path.exists()

    # ========================================================================
    # STORED ROOT
    # ========================================================================

    def stored_state_root(self) -> str | None:
        """Return persisted state root."""

        if not self.exists():
            return None

        connection = self._connect()

        try:

            value = self._get_metadata(
                connection,
                METADATA_STATE_ROOT,
            )

            if value is None:
                return None

            return str(value)

        finally:
            connection.close()

    # ========================================================================
    # STORED SUPPLY
    # ========================================================================

    def stored_total_supply(self) -> float | None:
        """Return persisted total supply."""

        if not self.exists():
            return None

        connection = self._connect()

        try:

            value = self._get_metadata(
                connection,
                METADATA_TOTAL_SUPPLY,
            )

            if value is None:
                return None

            return float(value)

        finally:
            connection.close()

    # ========================================================================
    # VERIFY
    # ========================================================================

    def verify(self) -> bool:
        """Fully verify persisted state."""

        self.load()

        return True

    # ========================================================================
    # SNAPSHOT
    # ========================================================================

    def snapshot(
        self,
        destination: str | Path,
    ) -> Path:
        """Create a verified database snapshot."""

        destination = Path(destination)

        destination.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        state = self.load()

        temp_dir = destination.parent

        temp_name = (
            f".{destination.name}.snapshot.tmp"
        )

        temp_path = temp_dir / temp_name

        if temp_path.exists():
            self._safe_delete_database_files(
                temp_path
            )

        snapshot_store = StateStore(
            temp_path
        )

        try:

            snapshot_store.save(state)

            snapshot_store.verify()

            self._safe_delete_database_files(
                destination
            )

            os.replace(
                str(temp_path),
                str(destination),
            )

            return destination

        finally:

            self._safe_delete_database_files(
                temp_path
            )

    # ========================================================================
    # ATOMIC REPLACEMENT
    # ========================================================================

    def replace(
        self,
        state: StateEngine,
    ) -> str:
        """
        Atomically replace the current database.
        """

        self._validate_state(state)

        state_root = self._calculate_state_root(
            state
        )

        parent = self.db_path.parent

        parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temp_name = tempfile.mkstemp(
            prefix=".nexchain_state_",
            suffix=".db",
            dir=str(parent),
        )

        os.close(fd)

        temp_path = Path(temp_name)

        try:

            self._safe_delete_database_files(
                temp_path
            )

            temp_store = StateStore(
                temp_path
            )

            temp_store.save(state)

            temp_store.verify()

            verified_root = (
                temp_store.stored_state_root()
            )

            if verified_root != state_root:
                raise StateStoreCorruptionError(
                    "Temporary state root verification failed."
                )

            del temp_store

            self._safe_delete_database_files(
                self.db_path
            )

            os.replace(
                str(temp_path),
                str(self.db_path),
            )

            return state_root

        finally:

            self._safe_delete_database_files(
                temp_path
            )

    # ========================================================================
    # CLEAR
    # ========================================================================

    def clear(self) -> None:
        """Completely remove persistent state."""

        self._safe_delete_database_files(
            self.db_path
        )

    # ========================================================================
    # WINDOWS-SAFE DATABASE CLEANUP
    # ========================================================================

    @staticmethod
    def _safe_delete_database_files(
        db_path: str | Path,
    ) -> None:

        db_path = Path(db_path)

        files = [
            db_path,
            Path(str(db_path) + "-wal"),
            Path(str(db_path) + "-shm"),
            Path(str(db_path) + "-journal"),
        ]

        for path in files:

            if not path.exists():
                continue

            try:

                path.unlink()

            except PermissionError:

                if path == db_path:
                    raise

    # ========================================================================
    # DATABASE STATISTICS
    # ========================================================================

    def stats(self) -> dict[str, Any]:
        """Return persistent database statistics."""

        if not self.exists():
            return {
                "exists": False,
                "database": str(self.db_path),
                "accounts": 0,
                "state_root": None,
                "total_supply": None,
                "schema_version": None,
            }

        connection = self._connect()

        try:

            row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM accounts
                """
            ).fetchone()

            account_count = int(
                row["count"]
            )

            version = self._get_metadata(
                connection,
                METADATA_SCHEMA_VERSION,
            )

            root = self._get_metadata(
                connection,
                METADATA_STATE_ROOT,
            )

            supply = self._get_metadata(
                connection,
                METADATA_TOTAL_SUPPLY,
            )

            return {
                "exists": True,
                "database": str(self.db_path),
                "accounts": account_count,
                "state_root": root,
                "total_supply": (
                    float(supply)
                    if supply is not None
                    else None
                ),
                "schema_version": (
                    int(version)
                    if version is not None
                    else None
                ),
            }

        finally:
            connection.close()

    # ========================================================================
    # SELF TEST
    # ========================================================================

    @classmethod
    def self_test(cls) -> None:

        print("=" * 66)
        print("NEXCHAIN PERSISTENT STATE STORE TEST")
        print("=" * 66)

        temp_directory = Path(
            tempfile.mkdtemp(
                prefix="nexchain_state_test_"
            )
        )

        database_path = (
            temp_directory / "state.db"
        )

        snapshot_path = (
            temp_directory / "snapshot.db"
        )

        try:

            # ---------------------------------------------------------------
            # 1. CREATE STORE
            # ---------------------------------------------------------------

            store = cls(
                database_path
            )

            print("[1/10] Database initialized")

            assert store.exists()

            # ---------------------------------------------------------------
            # 2. CREATE STATE
            # ---------------------------------------------------------------

            state = StateEngine()

            alice_address = (
                "NEX" + ("1" * 40)
            )

            bob_address = (
                "NEX" + ("2" * 40)
            )

            charlie_address = (
                "NEX" + ("3" * 40)
            )

            state.accounts[
                alice_address
            ] = Account(
                address=alice_address,
                balance=1000.0,
                nonce=0,
            )

            state.accounts[
                bob_address
            ] = Account(
                address=bob_address,
                balance=500.0,
                nonce=2,
            )

            state.total_supply = 1500.0

            print("[2/10] State created")

            # ---------------------------------------------------------------
            # 3. SAVE
            # ---------------------------------------------------------------

            root_1 = store.save(
                state
            )

            assert root_1 == state.state_root()

            print("[3/10] State saved")
            print(f"       Root: {root_1}")

            # ---------------------------------------------------------------
            # 4. LOAD
            # ---------------------------------------------------------------

            loaded = store.load()

            assert (
                loaded.accounts[
                    alice_address
                ].balance
                == 1000.0
            )

            assert (
                loaded.accounts[
                    bob_address
                ].balance
                == 500.0
            )

            assert (
                loaded.accounts[
                    bob_address
                ].nonce
                == 2
            )

            assert (
                loaded.total_supply
                == 1500.0
            )

            print(
                "[4/10] State loaded successfully"
            )

            # ---------------------------------------------------------------
            # 5. ROOT VERIFICATION
            # ---------------------------------------------------------------

            root_loaded = (
                loaded.state_root()
            )

            assert root_loaded == root_1

            assert (
                store.stored_state_root()
                == root_1
            )

            print(
                "[5/10] State root verified"
            )

            # ---------------------------------------------------------------
            # 6. STATE MODIFICATION
            # ---------------------------------------------------------------

            loaded.accounts[
                alice_address
            ].nonce = 7

            new_root = (
                loaded.state_root()
            )

            assert new_root != root_1

            root_2 = store.save(
                loaded
            )

            assert root_2 == new_root

            print(
                "[6/10] Modified state persisted"
            )

            # ---------------------------------------------------------------
            # 7. RELOAD MODIFIED STATE
            # ---------------------------------------------------------------

            restored = store.load()

            assert (
                restored.accounts[
                    alice_address
                ].nonce
                == 7
            )

            assert (
                restored.state_root()
                == root_2
            )

            print(
                "[7/10] Modified state recovered"
            )

            # ---------------------------------------------------------------
            # 8. SNAPSHOT
            # ---------------------------------------------------------------

            snapshot = store.snapshot(
                snapshot_path
            )

            assert snapshot.exists()

            snapshot_store = cls(
                snapshot_path
            )

            assert snapshot_store.verify()

            assert (
                snapshot_store.stored_state_root()
                == root_2
            )

            print(
                "[8/10] Snapshot created and verified"
            )

            # ---------------------------------------------------------------
            # 9. ATOMIC REPLACEMENT
            # ---------------------------------------------------------------

            replacement = StateEngine()

            replacement.accounts[
                charlie_address
            ] = Account(
                address=charlie_address,
                balance=2500.0,
                nonce=1,
            )

            replacement.total_supply = 2500.0

            replacement_root = (
                replacement.state_root()
            )

            returned_root = store.replace(
                replacement
            )

            assert (
                returned_root
                == replacement_root
            )

            recovered = store.load()

            assert (
                charlie_address
                in recovered.accounts
            )

            assert (
                recovered.accounts[
                    charlie_address
                ].balance
                == 2500.0
            )

            assert (
                recovered.total_supply
                == 2500.0
            )

            assert (
                recovered.state_root()
                == replacement_root
            )

            print(
                "[9/10] Atomic replacement verified"
            )

            # ---------------------------------------------------------------
            # 10. FINAL VERIFICATION
            # ---------------------------------------------------------------

            assert store.verify()

            statistics = store.stats()

            assert statistics["exists"] is True
            assert statistics["accounts"] == 1
            assert (
                statistics["state_root"]
                == replacement_root
            )
            assert (
                statistics["total_supply"]
                == 2500.0
            )
            assert (
                statistics["schema_version"]
                == SCHEMA_VERSION
            )

            print(
                "[10/10] Final integrity verification passed"
            )

            print()
            print("=" * 66)
            print("NEXCHAIN PERSISTENT STATE STORE: PASSED")
            print("=" * 66)
            print(
                f"Database : {database_path}"
            )
            print(
                f"Accounts : {statistics['accounts']}"
            )
            print(
                f"Supply   : {statistics['total_supply']}"
            )
            print(
                f"Root     : {statistics['state_root']}"
            )
            print(
                f"Schema   : {statistics['schema_version']}"
            )
            print("=" * 66)

        finally:

            for path in (
                database_path,
                snapshot_path,
            ):
                cls._safe_delete_database_files(
                    path
                )

            try:
                temp_directory.rmdir()
            except OSError:
                pass


# ============================================================================
# MODULE ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    StateStore.self_test()