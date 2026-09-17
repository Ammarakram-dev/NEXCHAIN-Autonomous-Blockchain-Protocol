"""
NEXCHAIN — Persistent Blockchain Store
======================================

Persistent Blockchain Storage

Responsibilities:
    - Persist complete blockchain to SQLite
    - Persist block metadata
    - Persist transactions
    - Recover blockchain after restart
    - Verify persisted data
    - Preserve state roots
    - Support database replacement
    - Provide database statistics
    - Detect persistent corruption

This module is part of the integrated NEXCHAIN protocol.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any

from core.block import Block
from core.blockchain import Blockchain
from core.transaction import Transaction


DEFAULT_DB_PATH = Path("data") / "nexchain_blockchain.db"

SCHEMA_VERSION = 1

METADATA_SCHEMA_VERSION = "schema_version"
METADATA_CHAIN_HEIGHT = "chain_height"
METADATA_CHAIN_LENGTH = "chain_length"
METADATA_LATEST_HASH = "latest_hash"
METADATA_CHAIN_DIGEST = "chain_digest"


class BlockchainStoreError(Exception):
    """Base persistent blockchain storage error."""


class BlockchainStoreCorruptionError(BlockchainStoreError):
    """Raised when persistent blockchain data is corrupted."""


class BlockchainStoreVersionError(BlockchainStoreError):
    """Raised when the database schema is unsupported."""


class BlockchainStoreRecoveryError(BlockchainStoreError):
    """Raised when blockchain recovery fails."""


class BlockchainStore:
    """
    SQLite-backed persistent storage for NEXCHAIN.

    Tables:
        metadata
        blocks
        transactions
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

    # ==================================================================
    # DATABASE
    # ==================================================================

    def _connect(self) -> sqlite3.Connection:
        """
        Open a database connection and guarantee that the current
        NEXCHAIN schema exists on that connection.

        This is intentionally defensive because the database may have
        been replaced, cleared, recreated, or recovered between runtime
        operations.
        """

        connection = sqlite3.connect(
            str(self.db_path),
            timeout=30.0,
        )

        connection.row_factory = sqlite3.Row

        connection.execute(
            "PRAGMA foreign_keys = ON"
        )

        connection.execute(
            "PRAGMA synchronous = FULL"
        )

        # --------------------------------------------------------------
        # Defensive schema initialization.
        #
        # Keep this schema identical to _initialize_database().
        # --------------------------------------------------------------

        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS blocks (
                height INTEGER PRIMARY KEY,
                block_hash TEXT NOT NULL UNIQUE,
                previous_hash TEXT NOT NULL,
                timestamp REAL NOT NULL,
                validator TEXT NOT NULL,
                state_root TEXT NOT NULL,
                block_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS transactions (
                tx_hash TEXT PRIMARY KEY,
                block_height INTEGER NOT NULL,
                tx_index INTEGER NOT NULL,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                nonce INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                tx_json TEXT NOT NULL,

                FOREIGN KEY(block_height)
                REFERENCES blocks(height)
                ON DELETE CASCADE,

                UNIQUE(block_height, tx_index)
            );

            CREATE INDEX IF NOT EXISTS
            idx_blocks_hash
            ON blocks(block_hash);

            CREATE INDEX IF NOT EXISTS
            idx_blocks_previous_hash
            ON blocks(previous_hash);

            CREATE INDEX IF NOT EXISTS
            idx_transactions_block
            ON transactions(block_height);

            CREATE INDEX IF NOT EXISTS
            idx_transactions_sender
            ON transactions(sender);

            CREATE INDEX IF NOT EXISTS
            idx_transactions_recipient
            ON transactions(recipient);
            """
        )

        connection.commit()

        return connection

    def _initialize_database(self) -> None:

        connection = self._connect()

        try:

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

                except (
                    TypeError,
                    ValueError,
                ) as exc:

                    raise BlockchainStoreVersionError(
                        "Invalid blockchain database schema version."
                    ) from exc

                if version != SCHEMA_VERSION:

                    raise BlockchainStoreVersionError(
                        f"Unsupported blockchain schema version: "
                        f"{version}. Expected {SCHEMA_VERSION}."
                    )

            connection.commit()

        finally:

            connection.close()

    # ==================================================================
    # METADATA
    # ==================================================================

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

        raw = row["value"]

        try:

            return json.loads(raw)

        except json.JSONDecodeError:

            return raw

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
            (
                key,
                encoded,
            ),
        )

    # ==================================================================
    # CANONICAL SERIALIZATION
    # ==================================================================

    @staticmethod
    def _canonical_json(
        value: Any,
    ) -> str:

        return json.dumps(
            value,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @classmethod
    def _calculate_chain_digest(
        cls,
        blockchain: Blockchain,
    ) -> str:

        block_hashes = [
            str(block.block_hash)
            for block in blockchain.chain
        ]

        payload = cls._canonical_json(
            block_hashes
        ).encode("utf-8")

        return hashlib.sha256(
            payload
        ).hexdigest()

    @classmethod
    def _block_json(
        cls,
        block: Block,
    ) -> str:

        return cls._canonical_json(
            block.to_dict()
        )

    @classmethod
    def _transaction_json(
        cls,
        transaction: Transaction,
    ) -> str:

        return cls._canonical_json(
            transaction.to_dict()
        )

    # ==================================================================
    # BLOCK VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_block(
        block: Block,
    ) -> None:

        if not isinstance(block, Block):

            raise BlockchainStoreCorruptionError(
                "Invalid block object."
            )

        if not isinstance(block.height, int):

            raise BlockchainStoreCorruptionError(
                "Block height must be an integer."
            )

        if block.height < 0:

            raise BlockchainStoreCorruptionError(
                "Block height cannot be negative."
            )

        if not isinstance(block.block_hash, str):

            raise BlockchainStoreCorruptionError(
                "Block hash must be a string."
            )

        if len(block.block_hash) != 64:

            raise BlockchainStoreCorruptionError(
                f"Invalid block hash length at height "
                f"{block.height}."
            )

        try:

            int(block.block_hash, 16)

        except ValueError as exc:

            raise BlockchainStoreCorruptionError(
                f"Invalid hexadecimal block hash at height "
                f"{block.height}."
            ) from exc

        if not isinstance(block.previous_hash, str):

            raise BlockchainStoreCorruptionError(
                "Previous block hash must be a string."
            )

        if len(block.previous_hash) != 64:

            raise BlockchainStoreCorruptionError(
                f"Invalid previous hash length at height "
                f"{block.height}."
            )

        try:

            int(block.previous_hash, 16)

        except ValueError as exc:

            raise BlockchainStoreCorruptionError(
                f"Invalid hexadecimal previous hash at height "
                f"{block.height}."
            ) from exc

        state_root = getattr(
            block,
            "state_root",
            "",
        )

        if state_root:

            if len(state_root) != 64:

                raise BlockchainStoreCorruptionError(
                    f"Invalid state root length at height "
                    f"{block.height}."
                )

            try:

                int(state_root, 16)

            except ValueError as exc:

                raise BlockchainStoreCorruptionError(
                    f"Invalid hexadecimal state root at height "
                    f"{block.height}."
                ) from exc

        try:

            result = block.validate()

        except Exception as exc:

            raise BlockchainStoreCorruptionError(
                f"Native block validation raised an error "
                f"at height {block.height}."
            ) from exc

        if isinstance(result, tuple):

            valid = bool(result[0])

            reason = (
                str(result[1])
                if len(result) > 1
                else "unknown validation failure"
            )

        else:

            valid = bool(result)
            reason = "native block validation failed"

        if not valid:

            raise BlockchainStoreCorruptionError(
                f"Block validation failed at height "
                f"{block.height}: {reason}"
            )

        for transaction in block.transactions:

            BlockchainStore._validate_transaction(
                transaction
            )

    # ==================================================================
    # TRANSACTION VALIDATION
    # ==================================================================

    @staticmethod
    def _validate_transaction(
        transaction: Transaction,
    ) -> None:

        if not isinstance(transaction, Transaction):

            raise BlockchainStoreCorruptionError(
                "Invalid transaction object."
            )

        try:

            result = transaction.validate()

        except Exception as exc:

            raise BlockchainStoreCorruptionError(
                "Transaction validation failed."
            ) from exc

        if isinstance(result, tuple):

            valid = bool(result[0])

            reason = (
                str(result[1])
                if len(result) > 1
                else "unknown transaction validation failure"
            )

        else:

            valid = bool(result)
            reason = "transaction validation failed"

        if not valid:

            raise BlockchainStoreCorruptionError(
                f"Invalid transaction: {reason}"
            )

    # ==================================================================
    # CHAIN STRUCTURE
    # ==================================================================

    @classmethod
    def _validate_chain_structure(
        cls,
        blockchain: Blockchain,
    ) -> None:

        if not blockchain.chain:

            raise BlockchainStoreRecoveryError(
                "Cannot persist an empty blockchain."
            )

        previous = None

        for expected_height, block in enumerate(
            blockchain.chain
        ):

            cls._validate_block(block)

            if block.height != expected_height:

                raise BlockchainStoreCorruptionError(
                    f"Invalid block height. "
                    f"Expected {expected_height}, "
                    f"got {block.height}."
                )

            if previous is not None:

                if block.previous_hash != previous.block_hash:

                    raise BlockchainStoreCorruptionError(
                        f"Broken chain linkage at height "
                        f"{block.height}."
                    )

            previous = block

    # ==================================================================
    # SAVE
    # ==================================================================

    def save(
        self,
        blockchain: Blockchain,
    ) -> str:

        if not isinstance(blockchain, Blockchain):

            raise TypeError(
                "blockchain must be a Blockchain instance."
            )

        self._validate_chain_structure(blockchain)

        try:

            result = blockchain.validate_chain()

        except Exception as exc:

            raise BlockchainStoreCorruptionError(
                "Blockchain validation failed."
            ) from exc

        if isinstance(result, tuple):

            valid = bool(result[0])

        else:

            valid = bool(result)

        if not valid:

            raise BlockchainStoreCorruptionError(
                "Blockchain cannot be persisted because "
                "validation failed."
            )

        chain_digest = self._calculate_chain_digest(
            blockchain
        )

        connection = self._connect()

        try:

            connection.execute(
                "BEGIN IMMEDIATE"
            )

            connection.execute(
                "DELETE FROM transactions"
            )

            connection.execute(
                "DELETE FROM blocks"
            )

            for block in blockchain.chain:

                connection.execute(
                    """
                    INSERT INTO blocks(
                        height,
                        block_hash,
                        previous_hash,
                        timestamp,
                        validator,
                        state_root,
                        block_json
                    )
                    VALUES(
                        ?, ?, ?, ?, ?, ?, ?
                    )
                    """,
                    (
                        int(block.height),
                        str(block.block_hash),
                        str(block.previous_hash),
                        float(block.timestamp),
                        str(block.validator),
                        str(
                            getattr(
                                block,
                                "state_root",
                                "",
                            )
                        ),
                        self._block_json(block),
                    ),
                )

                for tx_index, transaction in enumerate(
                    block.transactions
                ):

                    connection.execute(
                        """
                        INSERT INTO transactions(
                            tx_hash,
                            block_height,
                            tx_index,
                            sender,
                            recipient,
                            amount,
                            fee,
                            nonce,
                            timestamp,
                            tx_json
                        )
                        VALUES(
                            ?, ?, ?, ?, ?,
                            ?, ?, ?, ?, ?
                        )
                        """,
                        (
                            str(
                                transaction.transaction_hash()
                            ),
                            int(block.height),
                            int(tx_index),
                            str(transaction.sender),
                            str(transaction.recipient),
                            float(transaction.amount),
                            float(transaction.fee),
                            int(transaction.nonce),
                            float(transaction.timestamp),
                            self._transaction_json(
                                transaction
                            ),
                        ),
                    )

            latest = blockchain.chain[-1]

            self._set_metadata(
                connection,
                METADATA_SCHEMA_VERSION,
                SCHEMA_VERSION,
            )

            self._set_metadata(
                connection,
                METADATA_CHAIN_HEIGHT,
                int(latest.height),
            )

            self._set_metadata(
                connection,
                METADATA_CHAIN_LENGTH,
                len(blockchain.chain),
            )

            self._set_metadata(
                connection,
                METADATA_LATEST_HASH,
                str(latest.block_hash),
            )

            self._set_metadata(
                connection,
                METADATA_CHAIN_DIGEST,
                chain_digest,
            )

            connection.commit()

            return chain_digest

        except Exception:

            connection.rollback()
            raise

        finally:

            connection.close()

    # ==================================================================
    # LOAD / RECOVERY
    # ==================================================================

    def load(self) -> Blockchain:

        if not self.exists():

            raise BlockchainStoreRecoveryError(
                "Blockchain database does not exist."
            )

        connection = self._connect()

        try:

            version = self._get_metadata(
                connection,
                METADATA_SCHEMA_VERSION,
            )

            if version is None:

                raise BlockchainStoreVersionError(
                    "Blockchain schema version is missing."
                )

            if int(version) != SCHEMA_VERSION:

                raise BlockchainStoreVersionError(
                    f"Unsupported blockchain schema version: "
                    f"{version}."
                )

            rows = connection.execute(
                """
                SELECT
                    height,
                    block_json
                FROM blocks
                ORDER BY height ASC
                """
            ).fetchall()

            if not rows:

                raise BlockchainStoreRecoveryError(
                    "Persistent blockchain contains no blocks."
                )

            blocks: list[Block] = []

            for row in rows:

                try:

                    data = json.loads(
                        row["block_json"]
                    )

                    block = Block.from_dict(data)

                except Exception as exc:

                    raise BlockchainStoreCorruptionError(
                        f"Unable to decode block at "
                        f"height {row['height']}."
                    ) from exc

                if block.height != int(row["height"]):

                    raise BlockchainStoreCorruptionError(
                        "Persisted block height mismatch."
                    )

                self._validate_block(block)

                blocks.append(block)

            transaction_rows = connection.execute(
                """
                SELECT
                    tx_hash,
                    block_height,
                    tx_index,
                    tx_json
                FROM transactions
                ORDER BY
                    block_height ASC,
                    tx_index ASC
                """
            ).fetchall()

            persisted_transactions: dict[
                tuple[int, int],
                str,
            ] = {}

            for row in transaction_rows:

                key = (
                    int(row["block_height"]),
                    int(row["tx_index"]),
                )

                try:

                    tx_data = json.loads(
                        row["tx_json"]
                    )

                    transaction = Transaction.from_dict(
                        tx_data
                    )

                except Exception as exc:

                    raise BlockchainStoreCorruptionError(
                        "Unable to decode persisted transaction."
                    ) from exc

                self._validate_transaction(transaction)

                calculated_hash = (
                    transaction.transaction_hash()
                )

                if calculated_hash != str(row["tx_hash"]):

                    raise BlockchainStoreCorruptionError(
                        "Persisted transaction hash mismatch."
                    )

                persisted_transactions[key] = str(
                    row["tx_hash"]
                )

            expected_transaction_count = 0

            for block in blocks:

                for tx_index, transaction in enumerate(
                    block.transactions
                ):

                    expected_transaction_count += 1

                    key = (
                        int(block.height),
                        int(tx_index),
                    )

                    if key not in persisted_transactions:

                        raise BlockchainStoreCorruptionError(
                            f"Transaction missing from persistent "
                            f"transaction table at block "
                            f"{block.height}, index {tx_index}."
                        )

                    if (
                        persisted_transactions[key]
                        != transaction.transaction_hash()
                    ):

                        raise BlockchainStoreCorruptionError(
                            "Block transaction hash does not "
                            "match transaction table."
                        )

            if (
                expected_transaction_count
                != len(persisted_transactions)
            ):

                raise BlockchainStoreCorruptionError(
                    "Persistent transaction table contains "
                    "unexpected records."
                )

            genesis = blocks[0]

            blockchain = Blockchain(
                genesis_validator=str(
                    genesis.validator
                )
            )

            generated_genesis = blockchain.chain[0]

            if generated_genesis.block_hash != genesis.block_hash:

                raise BlockchainStoreCorruptionError(
                    "Persisted genesis block does not match "
                    "the NEXCHAIN genesis configuration."
                )

            if generated_genesis.height != genesis.height:

                raise BlockchainStoreCorruptionError(
                    "Persisted genesis height mismatch."
                )

            if (
                generated_genesis.previous_hash
                != genesis.previous_hash
            ):

                raise BlockchainStoreCorruptionError(
                    "Persisted genesis previous hash mismatch."
                )

            for block in blocks[1:]:

                result = blockchain.add_block(block)

                if isinstance(result, tuple):

                    if not bool(result[0]):

                        raise BlockchainStoreRecoveryError(
                            f"Unable to recover block "
                            f"{block.height}: {result}"
                        )

                elif result is False:

                    raise BlockchainStoreRecoveryError(
                        f"Unable to recover block "
                        f"{block.height}."
                    )

            self._validate_chain_structure(blockchain)

            try:

                result = blockchain.validate_chain()

            except Exception as exc:

                raise BlockchainStoreRecoveryError(
                    "Recovered blockchain validation failed."
                ) from exc

            if isinstance(result, tuple):

                valid = bool(result[0])

            else:

                valid = bool(result)

            if not valid:

                raise BlockchainStoreRecoveryError(
                    "Recovered blockchain is invalid."
                )

            latest = blockchain.chain[-1]

            stored_height = self._get_metadata(
                connection,
                METADATA_CHAIN_HEIGHT,
            )

            stored_length = self._get_metadata(
                connection,
                METADATA_CHAIN_LENGTH,
            )

            stored_latest_hash = self._get_metadata(
                connection,
                METADATA_LATEST_HASH,
            )

            stored_digest = self._get_metadata(
                connection,
                METADATA_CHAIN_DIGEST,
            )

            if int(stored_height) != latest.height:

                raise BlockchainStoreCorruptionError(
                    "Stored chain height does not match blockchain."
                )

            if int(stored_length) != len(blockchain.chain):

                raise BlockchainStoreCorruptionError(
                    "Stored chain length does not match blockchain."
                )

            if str(stored_latest_hash) != latest.block_hash:

                raise BlockchainStoreCorruptionError(
                    "Stored latest hash does not match blockchain."
                )

            calculated_digest = self._calculate_chain_digest(
                blockchain
            )

            if str(stored_digest) != calculated_digest:

                raise BlockchainStoreCorruptionError(
                    "Stored chain digest does not match blockchain."
                )

            return blockchain

        finally:

            connection.close()

    # ==================================================================
    # LOOKUPS
    # ==================================================================

    def exists(self) -> bool:

        return self.db_path.exists()

    def verify(self) -> bool:

        self.load()

        return True

    def get_block(
        self,
        height: int,
    ) -> Block | None:

        if not self.exists():
            return None

        connection = self._connect()

        try:

            row = connection.execute(
                """
                SELECT block_json
                FROM blocks
                WHERE height = ?
                """,
                (int(height),),
            ).fetchone()

            if row is None:
                return None

            try:

                block = Block.from_dict(
                    json.loads(row["block_json"])
                )

            except Exception as exc:

                raise BlockchainStoreCorruptionError(
                    f"Unable to decode block {height}."
                ) from exc

            self._validate_block(block)

            return block

        finally:

            connection.close()

    def get_transaction(
        self,
        transaction_hash: str,
    ) -> Transaction | None:

        if not self.exists():
            return None

        connection = self._connect()

        try:

            row = connection.execute(
                """
                SELECT tx_json
                FROM transactions
                WHERE tx_hash = ?
                """,
                (str(transaction_hash),),
            ).fetchone()

            if row is None:
                return None

            try:

                transaction = Transaction.from_dict(
                    json.loads(row["tx_json"])
                )

            except Exception as exc:

                raise BlockchainStoreCorruptionError(
                    "Unable to decode transaction."
                ) from exc

            self._validate_transaction(transaction)

            if (
                transaction.transaction_hash()
                != str(transaction_hash)
            ):

                raise BlockchainStoreCorruptionError(
                    "Transaction hash verification failed."
                )

            return transaction

        finally:

            connection.close()

    def latest_block(self) -> Block | None:

        if not self.exists():
            return None

        connection = self._connect()

        try:

            row = connection.execute(
                """
                SELECT block_json
                FROM blocks
                ORDER BY height DESC
                LIMIT 1
                """
            ).fetchone()

            if row is None:
                return None

            block = Block.from_dict(
                json.loads(row["block_json"])
            )

            self._validate_block(block)

            return block

        finally:

            connection.close()

    # ==================================================================
    # STATISTICS
    # ==================================================================

    def stats(self) -> dict[str, Any]:

        if not self.exists():

            return {
                "exists": False,
                "database": str(self.db_path),
                "blocks": 0,
                "transactions": 0,
                "height": None,
                "latest_hash": None,
                "chain_digest": None,
                "schema_version": None,
            }

        connection = self._connect()

        try:

            block_row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM blocks
                """
            ).fetchone()

            transaction_row = connection.execute(
                """
                SELECT COUNT(*) AS count
                FROM transactions
                """
            ).fetchone()

            return {
                "exists": True,
                "database": str(self.db_path),
                "blocks": int(block_row["count"]),
                "transactions": int(
                    transaction_row["count"]
                ),
                "height": self._get_metadata(
                    connection,
                    METADATA_CHAIN_HEIGHT,
                ),
                "latest_hash": self._get_metadata(
                    connection,
                    METADATA_LATEST_HASH,
                ),
                "chain_digest": self._get_metadata(
                    connection,
                    METADATA_CHAIN_DIGEST,
                ),
                "schema_version": self._get_metadata(
                    connection,
                    METADATA_SCHEMA_VERSION,
                ),
            }

        finally:

            connection.close()

    # ==================================================================
    # DATABASE REPLACEMENT
    # ==================================================================

    def replace(
        self,
        blockchain: Blockchain,
    ) -> str:

        if not isinstance(blockchain, Blockchain):

            raise TypeError(
                "blockchain must be a Blockchain instance."
            )

        self._validate_chain_structure(blockchain)

        parent = self.db_path.parent

        parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temporary_name = tempfile.mkstemp(
            prefix=".nexchain_chain_",
            suffix=".db",
            dir=str(parent),
        )

        os.close(fd)

        temporary_path = Path(temporary_name)

        try:

            self._safe_delete_database_files(
                temporary_path
            )

            temporary_store = BlockchainStore(
                temporary_path
            )

            digest = temporary_store.save(
                blockchain
            )

            temporary_store.verify()

            del temporary_store

            self._safe_delete_database_files(
                self.db_path
            )

            os.replace(
                str(temporary_path),
                str(self.db_path),
            )

            return digest

        finally:

            self._safe_delete_database_files(
                temporary_path
            )

    def clear(self) -> None:

        self._safe_delete_database_files(
            self.db_path
        )

    @staticmethod
    def _safe_delete_database_files(
        db_path: str | Path,
    ) -> None:

        db_path = Path(db_path)

        paths = [
            db_path,
            Path(str(db_path) + "-wal"),
            Path(str(db_path) + "-shm"),
            Path(str(db_path) + "-journal"),
        ]

        for path in paths:

            if not path.exists():
                continue

            try:

                path.unlink()

            except PermissionError:

                if path == db_path:
                    raise

    # ==================================================================
    # SELF TEST
    # ==================================================================

    @classmethod
    def self_test(cls) -> None:

        print("=" * 66)
        print(
            "NEXCHAIN PERSISTENT BLOCKCHAIN STORE TEST"
        )
        print("=" * 66)

        temporary_directory = Path(
            tempfile.mkdtemp(
                prefix="nexchain_blockchain_test_"
            )
        )

        database_path = (
            temporary_directory / "blockchain.db"
        )

        try:

            validator = "NEX" + ("9" * 40)

            blockchain = Blockchain(
                genesis_validator=validator
            )

            print("[1/10] Blockchain initialized")

            state_root_1 = hashlib.sha256(
                b"state-1"
            ).hexdigest()

            state_root_2 = hashlib.sha256(
                b"state-2"
            ).hexdigest()

            latest = blockchain.latest_block

            block_1 = Block(
                version=1,
                height=latest.height + 1,
                previous_hash=latest.block_hash,
                timestamp=1_700_000_001.0,
                validator=validator,
                nonce=1,
                difficulty=0,
                transactions=[],
                state_root=state_root_1,
            )

            block_1.finalize()

            result = blockchain.add_block(block_1)

            if isinstance(result, tuple):

                if not bool(result[0]):

                    raise BlockchainStoreError(
                        f"Block 1 rejected: {result}"
                    )

            elif result is False:

                raise BlockchainStoreError(
                    "Block 1 was rejected."
                )

            print(
                "[2/10] First persistent test block created"
            )

            latest = blockchain.latest_block

            block_2 = Block(
                version=1,
                height=latest.height + 1,
                previous_hash=latest.block_hash,
                timestamp=1_700_000_002.0,
                validator=validator,
                nonce=2,
                difficulty=0,
                transactions=[],
                state_root=state_root_2,
            )

            block_2.finalize()

            result = blockchain.add_block(block_2)

            if isinstance(result, tuple):

                if not bool(result[0]):

                    raise BlockchainStoreError(
                        f"Block 2 rejected: {result}"
                    )

            elif result is False:

                raise BlockchainStoreError(
                    "Block 2 was rejected."
                )

            print(
                "[3/10] Second persistent test block created"
            )

            store = cls(database_path)

            print(
                "[4/10] Persistent store initialized"
            )

            digest = store.save(blockchain)

            assert store.exists()
            assert isinstance(digest, str)
            assert len(digest) == 64

            print(
                "[5/10] Complete blockchain persisted"
            )

            recovered = store.load()

            assert len(recovered.chain) == len(
                blockchain.chain
            )

            for original, restored in zip(
                blockchain.chain,
                recovered.chain,
            ):

                assert (
                    original.height
                    == restored.height
                )

                assert (
                    original.block_hash
                    == restored.block_hash
                )

                assert (
                    original.previous_hash
                    == restored.previous_hash
                )

                assert (
                    original.state_root
                    == restored.state_root
                )

            print(
                "[6/10] Blockchain recovered successfully"
            )

            loaded_block = store.get_block(
                block_2.height
            )

            assert loaded_block is not None

            assert (
                loaded_block.block_hash
                == block_2.block_hash
            )

            assert (
                store.get_transaction("0" * 64)
                is None
            )

            latest_loaded = store.latest_block()

            assert latest_loaded is not None

            assert (
                latest_loaded.block_hash
                == block_2.block_hash
            )

            print(
                "[7/10] Persistent lookup verified"
            )

            assert store.verify()

            statistics = store.stats()

            assert (
                statistics["blocks"]
                == len(blockchain.chain)
            )

            assert (
                statistics["height"]
                == block_2.height
            )

            assert (
                statistics["latest_hash"]
                == block_2.block_hash
            )

            assert (
                statistics["chain_digest"]
                == digest
            )

            print(
                "[8/10] Integrity verification passed"
            )

            restarted_store = cls(database_path)

            restarted_chain = restarted_store.load()

            assert (
                restarted_chain.latest_block.block_hash
                == blockchain.latest_block.block_hash
            )

            assert (
                restarted_chain.latest_block.height
                == blockchain.latest_block.height
            )

            assert restarted_store.verify() is True

            print(
                "[9/10] Restart recovery passed"
            )

            final_stats = restarted_store.stats()

            assert final_stats["blocks"] == 3
            assert final_stats["transactions"] == 0

            print(
                "[10/10] Final persistent storage test passed"
            )

            print()
            print("=" * 66)
            print(
                "NEXCHAIN PERSISTENT BLOCKCHAIN STORE: PASSED"
            )
            print("=" * 66)

            print(
                f"Blocks       : {final_stats['blocks']}"
            )

            print(
                f"Transactions : {final_stats['transactions']}"
            )

            print(
                f"Height       : {final_stats['height']}"
            )

            print(
                f"Latest Hash  : {final_stats['latest_hash']}"
            )

            print(
                f"Chain Digest : {final_stats['chain_digest']}"
            )

            print(
                f"Schema       : {final_stats['schema_version']}"
            )

            print("=" * 66)

        finally:

            cls._safe_delete_database_files(
                database_path
            )

            try:

                temporary_directory.rmdir()

            except OSError:

                pass


if __name__ == "__main__":
    BlockchainStore.self_test()