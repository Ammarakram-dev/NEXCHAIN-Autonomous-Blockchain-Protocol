"""
NEXCHAIN Persistent Storage Engine
==================================

SQLite-backed persistence for the NEXCHAIN blockchain.

The database stores:
    - Blocks
    - Transactions
    - Chain metadata

The storage layer deliberately remains independent from
the networking and UI layers.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any


# ============================================================
# DATABASE
# ============================================================

class NEXChainDatabase:

    def __init__(self, database_path: str = "data/nexchain.db"):

        self.database_path = Path(database_path)

        self.database_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.connection = sqlite3.connect(
            self.database_path,
            check_same_thread=False,
        )

        self.connection.row_factory = sqlite3.Row

        self._initialize()

    # ========================================================
    # INITIALIZATION
    # ========================================================

    def _initialize(self) -> None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS blocks (
                height INTEGER PRIMARY KEY,
                block_hash TEXT UNIQUE NOT NULL,
                previous_hash TEXT NOT NULL,
                merkle_root TEXT NOT NULL,
                timestamp REAL NOT NULL,
                validator TEXT NOT NULL,
                nonce INTEGER NOT NULL,
                difficulty INTEGER NOT NULL,
                version INTEGER NOT NULL,
                block_data TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS transactions (
                transaction_hash TEXT PRIMARY KEY,
                block_height INTEGER NOT NULL,
                sender TEXT NOT NULL,
                recipient TEXT NOT NULL,
                amount REAL NOT NULL,
                fee REAL NOT NULL,
                nonce INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                transaction_data TEXT NOT NULL,
                FOREIGN KEY(block_height)
                    REFERENCES blocks(height)
            )
            """
        )

        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            )
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tx_sender
            ON transactions(sender)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tx_recipient
            ON transactions(recipient)
            """
        )

        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_tx_block
            ON transactions(block_height)
            """
        )

        self.connection.commit()

    # ========================================================
    # BLOCK
    # ========================================================

    def save_block(self, block: Any) -> None:

        block_data = block.to_dict()

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO blocks (
                height,
                block_hash,
                previous_hash,
                merkle_root,
                timestamp,
                validator,
                nonce,
                difficulty,
                version,
                block_data
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                block.height,
                block.block_hash,
                block.previous_hash,
                block.merkle_root,
                block.timestamp,
                block.validator,
                block.nonce,
                block.difficulty,
                block.version,
                json.dumps(
                    block_data,
                    sort_keys=True,
                ),
            ),
        )

        for transaction in block.transactions:

            tx_data = transaction.to_dict()

            cursor.execute(
                """
                INSERT OR REPLACE INTO transactions (
                    transaction_hash,
                    block_height,
                    sender,
                    recipient,
                    amount,
                    fee,
                    nonce,
                    timestamp,
                    transaction_data
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    transaction.transaction_hash(),
                    block.height,
                    transaction.sender,
                    transaction.recipient,
                    transaction.amount,
                    transaction.fee,
                    transaction.nonce,
                    transaction.timestamp,
                    json.dumps(
                        tx_data,
                        sort_keys=True,
                    ),
                ),
            )

        self.connection.commit()

    # ========================================================
    # BLOCK LOOKUP
    # ========================================================

    def get_block(self, height: int) -> dict | None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT block_data
            FROM blocks
            WHERE height = ?
            """,
            (height,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return json.loads(row["block_data"])

    # ========================================================
    # BLOCK BY HASH
    # ========================================================

    def get_block_by_hash(
        self,
        block_hash: str,
    ) -> dict | None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT block_data
            FROM blocks
            WHERE block_hash = ?
            """,
            (block_hash,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return json.loads(row["block_data"])

    # ========================================================
    # TRANSACTION LOOKUP
    # ========================================================

    def get_transaction(
        self,
        transaction_hash: str,
    ) -> dict | None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT transaction_data
            FROM transactions
            WHERE transaction_hash = ?
            """,
            (transaction_hash,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return json.loads(row["transaction_data"])

    # ========================================================
    # LATEST BLOCK
    # ========================================================

    def get_latest_block(self) -> dict | None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT block_data
            FROM blocks
            ORDER BY height DESC
            LIMIT 1
            """
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return json.loads(row["block_data"])

    # ========================================================
    # CHAIN HEIGHT
    # ========================================================

    def get_height(self) -> int:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT MAX(height) AS height
            FROM blocks
            """
        )

        row = cursor.fetchone()

        if row["height"] is None:
            return -1

        return int(row["height"])

    # ========================================================
    # BLOCK COUNT
    # ========================================================

    def get_block_count(self) -> int:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM blocks
            """
        )

        return int(cursor.fetchone()["count"])

    # ========================================================
    # TRANSACTION COUNT
    # ========================================================

    def get_transaction_count(self) -> int:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT COUNT(*) AS count
            FROM transactions
            """
        )

        return int(cursor.fetchone()["count"])

    # ========================================================
    # METADATA
    # ========================================================

    def set_metadata(
        self,
        key: str,
        value: str,
    ) -> None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO metadata (
                key,
                value
            )
            VALUES (?, ?)
            """,
            (key, value),
        )

        self.connection.commit()

    def get_metadata(
        self,
        key: str,
    ) -> str | None:

        cursor = self.connection.cursor()

        cursor.execute(
            """
            SELECT value
            FROM metadata
            WHERE key = ?
            """,
            (key,),
        )

        row = cursor.fetchone()

        if row is None:
            return None

        return row["value"]

    # ========================================================
    # DATABASE STATS
    # ========================================================

    def stats(self) -> dict[str, int]:

        return {
            "blocks": self.get_block_count(),
            "transactions": self.get_transaction_count(),
            "height": self.get_height(),
        }

    # ========================================================
    # CLOSE
    # ========================================================

    def close(self) -> None:

        self.connection.close()


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    import os
    import tempfile

    from crypto.crypto_engine import Wallet
    from core.transaction import create_transaction
    from core.block import create_block

    print("=" * 60)
    print("NEXCHAIN STORAGE ENGINE TEST")
    print("=" * 60)

    # --------------------------------------------------------
    # Temporary database
    # --------------------------------------------------------

    temp_dir = tempfile.mkdtemp(
        prefix="nexchain_test_"
    )

    database_path = os.path.join(
        temp_dir,
        "test.db",
    )

    db = NEXChainDatabase(database_path)

    # --------------------------------------------------------
    # Create wallets
    # --------------------------------------------------------

    validator = Wallet.generate()
    sender = Wallet.generate()
    recipient = Wallet.generate()

    # --------------------------------------------------------
    # Transaction
    # --------------------------------------------------------

    transaction = create_transaction(
        wallet=sender,
        recipient=recipient.address(),
        amount=100,
        fee=0.01,
        nonce=0,
    )

    # --------------------------------------------------------
    # Block
    # --------------------------------------------------------

    block = create_block(
        height=0,
        previous_hash="0" * 64,
        validator=validator.address(),
        transactions=[transaction],
    )

    # --------------------------------------------------------
    # Save
    # --------------------------------------------------------

    db.save_block(block)

    print()
    print("[PASS] Database initialization")
    print("[PASS] Block persistence")
    print("[PASS] Transaction persistence")

    # --------------------------------------------------------
    # Retrieve block
    # --------------------------------------------------------

    stored_block = db.get_block(0)

    assert stored_block is not None
    assert stored_block["block_hash"] == block.block_hash

    print("[PASS] Block retrieval")

    # --------------------------------------------------------
    # Retrieve transaction
    # --------------------------------------------------------

    stored_transaction = db.get_transaction(
        transaction.transaction_hash()
    )

    assert stored_transaction is not None

    print("[PASS] Transaction retrieval")

    # --------------------------------------------------------
    # Latest block
    # --------------------------------------------------------

    latest = db.get_latest_block()

    assert latest is not None
    assert latest["height"] == 0

    print("[PASS] Latest block lookup")

    # --------------------------------------------------------
    # Metadata
    # --------------------------------------------------------

    db.set_metadata(
        "network",
        "nexchain-devnet",
    )

    assert db.get_metadata("network") == "nexchain-devnet"

    print("[PASS] Metadata storage")

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    stats = db.stats()

    assert stats["blocks"] == 1
    assert stats["transactions"] == 1
    assert stats["height"] == 0

    print("[PASS] Database statistics")

    db.close()

    print()
    print("=" * 60)
    print("ALL STORAGE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    self_test()