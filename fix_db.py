import sqlite3
from pathlib import Path

db = Path("data/nexchain_blockchain.db")
db.parent.mkdir(parents=True, exist_ok=True)

conn = sqlite3.connect(db)

conn.executescript("""
CREATE TABLE IF NOT EXISTS metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS blocks (
    height INTEGER PRIMARY KEY,
    version INTEGER NOT NULL,
    previous_hash TEXT NOT NULL,
    timestamp REAL NOT NULL,
    validator TEXT NOT NULL,
    nonce INTEGER NOT NULL,
    difficulty INTEGER NOT NULL,
    merkle_root TEXT NOT NULL,
    block_hash TEXT NOT NULL UNIQUE,
    state_root TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS transactions (
    transaction_hash TEXT PRIMARY KEY,
    block_height INTEGER NOT NULL,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    amount REAL NOT NULL,
    fee REAL NOT NULL,
    nonce INTEGER NOT NULL,
    timestamp REAL NOT NULL,
    public_key TEXT NOT NULL,
    signature TEXT NOT NULL,
    FOREIGN KEY(block_height) REFERENCES blocks(height)
);

CREATE INDEX IF NOT EXISTS idx_blocks_hash
ON blocks(block_hash);

CREATE INDEX IF NOT EXISTS idx_blocks_previous_hash
ON blocks(previous_hash);

CREATE INDEX IF NOT EXISTS idx_transactions_block
ON transactions(block_height);

CREATE INDEX IF NOT EXISTS idx_transactions_sender
ON transactions(sender);

CREATE INDEX IF NOT EXISTS idx_transactions_recipient
ON transactions(recipient);
""")

conn.commit()

tables = conn.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
).fetchall()

print("DATABASE:", db.resolve())
print("TABLES:", tables)

conn.close()
print("Database schema repaired successfully.")