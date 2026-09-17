"""
NEXCHAIN — Blockchain Recovery Engine
=====================================

STEP 13
Blockchain Recovery + Persistent State Coordination

Responsibilities:
    - Recover blockchain state after restart
    - Verify persistent state
    - Verify state roots
    - Coordinate blockchain + state storage
    - Create recovery checkpoints
    - Restore verified state
    - Detect blockchain/state mismatches
    - Provide deterministic recovery status

Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from core.blockchain import Blockchain
from core.block import Block
from core.state import Account, StateEngine
from storage.state_store import (
    StateStore,
    StateStoreError,
)


# ============================================================================
# CONSTANTS
# ============================================================================

RECOVERY_VERSION = 1

DEFAULT_RECOVERY_DIR = (
    Path("data") / "recovery"
)

DEFAULT_CHECKPOINT_FILE = (
    DEFAULT_RECOVERY_DIR / "checkpoint.json"
)


# ============================================================================
# EXCEPTIONS
# ============================================================================

class RecoveryError(Exception):
    """Base recovery exception."""


class RecoveryIntegrityError(RecoveryError):
    """Raised when recovery integrity verification fails."""


class RecoveryCheckpointError(RecoveryError):
    """Raised when a checkpoint is invalid."""


class RecoveryStateMismatchError(RecoveryError):
    """Raised when blockchain and state do not agree."""


# ============================================================================
# CHECKPOINT
# ============================================================================

@dataclass(frozen=True)
class RecoveryCheckpoint:
    """
    Immutable description of the last coordinated
    blockchain + state recovery point.
    """

    version: int
    block_height: int
    block_hash: str
    previous_block_hash: str
    state_root: str
    state_supply: float
    chain_length: int
    timestamp: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "block_height": self.block_height,
            "block_hash": self.block_hash,
            "previous_block_hash": self.previous_block_hash,
            "state_root": self.state_root,
            "state_supply": self.state_supply,
            "chain_length": self.chain_length,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "RecoveryCheckpoint":

        if not isinstance(data, dict):
            raise RecoveryCheckpointError(
                "Checkpoint must be a JSON object."
            )

        required = {
            "version",
            "block_height",
            "block_hash",
            "previous_block_hash",
            "state_root",
            "state_supply",
            "chain_length",
            "timestamp",
        }

        missing = required - set(data.keys())

        if missing:
            raise RecoveryCheckpointError(
                f"Checkpoint missing fields: {sorted(missing)}"
            )

        try:
            checkpoint = cls(
                version=int(data["version"]),
                block_height=int(data["block_height"]),
                block_hash=str(data["block_hash"]),
                previous_block_hash=str(
                    data["previous_block_hash"]
                ),
                state_root=str(data["state_root"]),
                state_supply=float(data["state_supply"]),
                chain_length=int(data["chain_length"]),
                timestamp=float(data["timestamp"]),
            )
        except (TypeError, ValueError) as exc:
            raise RecoveryCheckpointError(
                "Checkpoint contains invalid values."
            ) from exc

        checkpoint.validate()

        return checkpoint

    def validate(self) -> None:

        if self.version != RECOVERY_VERSION:
            raise RecoveryCheckpointError(
                f"Unsupported checkpoint version: "
                f"{self.version}"
            )

        if self.block_height < 0:
            raise RecoveryCheckpointError(
                "Block height cannot be negative."
            )

        if self.chain_length <= 0:
            raise RecoveryCheckpointError(
                "Chain length must be positive."
            )

        if self.chain_length != self.block_height + 1:
            raise RecoveryCheckpointError(
                "Chain length does not match block height."
            )

        if len(self.block_hash) != 64:
            raise RecoveryCheckpointError(
                "Block hash must contain 64 hexadecimal characters."
            )

        if len(self.previous_block_hash) != 64:
            raise RecoveryCheckpointError(
                "Previous block hash must contain 64 hexadecimal characters."
            )

        if len(self.state_root) != 64:
            raise RecoveryCheckpointError(
                "State root must contain 64 hexadecimal characters."
            )

        for value, label in (
            (self.block_hash, "block hash"),
            (
                self.previous_block_hash,
                "previous block hash",
            ),
            (self.state_root, "state root"),
        ):
            try:
                int(value, 16)
            except ValueError as exc:
                raise RecoveryCheckpointError(
                    f"Invalid hexadecimal {label}."
                ) from exc

        if self.state_supply < 0:
            raise RecoveryCheckpointError(
                "State supply cannot be negative."
            )

        if self.timestamp <= 0:
            raise RecoveryCheckpointError(
                "Checkpoint timestamp must be positive."
            )


# ============================================================================
# RECOVERY ENGINE
# ============================================================================

class RecoveryEngine:
    """
    Coordinates persistent blockchain state and recovery.

    Recovery architecture:

        Blockchain
             |
             v
        Latest Block
             |
             v
        Recovery Checkpoint
             |
             v
        Persistent State
             |
             v
        State Root
             |
             v
        Integrity Verification
    """

    def __init__(
        self,
        blockchain: Blockchain,
        state_store: StateStore,
        checkpoint_path: str | Path = DEFAULT_CHECKPOINT_FILE,
    ) -> None:

        if not isinstance(
            blockchain,
            Blockchain,
        ):
            raise TypeError(
                "blockchain must be a Blockchain instance."
            )

        if not isinstance(
            state_store,
            StateStore,
        ):
            raise TypeError(
                "state_store must be a StateStore instance."
            )

        self.blockchain = blockchain
        self.state_store = state_store

        self.checkpoint_path = Path(
            checkpoint_path
        )

        self.checkpoint_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

    # ========================================================================
    # CHECKPOINT HASH
    # ========================================================================

    @staticmethod
    def _hash_checkpoint(
        checkpoint: RecoveryCheckpoint,
    ) -> str:

        payload = json.dumps(
            checkpoint.to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(
            payload
        ).hexdigest()

    # ========================================================================
    # CREATE CHECKPOINT
    # ========================================================================

    def create_checkpoint(
        self,
        state: StateEngine,
    ) -> RecoveryCheckpoint:
        """
        Create a recovery checkpoint for the current
        blockchain tip and state.
        """

        if not isinstance(
            state,
            StateEngine,
        ):
            raise TypeError(
                "state must be a StateEngine instance."
            )

        if not self.blockchain.chain:
            raise RecoveryError(
                "Cannot create checkpoint from an empty blockchain."
            )

        latest_block = (
            self.blockchain.chain[-1]
        )

        state_root = state.state_root()

        checkpoint = RecoveryCheckpoint(
            version=RECOVERY_VERSION,
            block_height=int(
                latest_block.height
            ),
            block_hash=str(
                latest_block.block_hash
            ),
            previous_block_hash=str(
                latest_block.previous_hash
            ),
            state_root=str(
                state_root
            ),
            state_supply=float(
                state.total_supply
            ),
            chain_length=len(
                self.blockchain.chain
            ),
            timestamp=float(
                latest_block.timestamp
            ),
        )

        checkpoint.validate()

        return checkpoint

    # ========================================================================
    # SAVE CHECKPOINT
    # ========================================================================

    def save_checkpoint(
        self,
        checkpoint: RecoveryCheckpoint,
    ) -> Path:
        """
        Atomically save a verified checkpoint.
        """

        checkpoint.validate()

        payload = {
            "checkpoint": checkpoint.to_dict(),
            "integrity": self._hash_checkpoint(
                checkpoint
            ),
        }

        self.checkpoint_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        fd, temporary_name = tempfile.mkstemp(
            prefix=".nexchain_checkpoint_",
            suffix=".tmp",
            dir=str(
                self.checkpoint_path.parent
            ),
        )

        os.close(fd)

        temporary_path = Path(
            temporary_name
        )

        try:

            temporary_path.write_text(
                json.dumps(
                    payload,
                    indent=2,
                    sort_keys=True,
                ),
                encoding="utf-8",
            )

            os.replace(
                str(temporary_path),
                str(self.checkpoint_path),
            )

            return self.checkpoint_path

        finally:

            if temporary_path.exists():
                try:
                    temporary_path.unlink()
                except OSError:
                    pass

    # ========================================================================
    # LOAD CHECKPOINT
    # ========================================================================

    def load_checkpoint(
        self,
    ) -> RecoveryCheckpoint:
        """
        Load and verify the recovery checkpoint.
        """

        if not self.checkpoint_path.exists():
            raise RecoveryCheckpointError(
                "Recovery checkpoint does not exist."
            )

        try:

            raw = self.checkpoint_path.read_text(
                encoding="utf-8"
            )

            payload = json.loads(raw)

        except (
            OSError,
            json.JSONDecodeError,
        ) as exc:

            raise RecoveryCheckpointError(
                "Unable to read recovery checkpoint."
            ) from exc

        if not isinstance(payload, dict):
            raise RecoveryCheckpointError(
                "Invalid checkpoint container."
            )

        checkpoint_data = payload.get(
            "checkpoint"
        )

        stored_integrity = payload.get(
            "integrity"
        )

        if checkpoint_data is None:
            raise RecoveryCheckpointError(
                "Checkpoint payload is missing."
            )

        if not isinstance(
            stored_integrity,
            str,
        ):
            raise RecoveryCheckpointError(
                "Checkpoint integrity is missing."
            )

        checkpoint = (
            RecoveryCheckpoint.from_dict(
                checkpoint_data
            )
        )

        calculated_integrity = (
            self._hash_checkpoint(
                checkpoint
            )
        )

        if calculated_integrity != stored_integrity:
            raise RecoveryCheckpointError(
                "Checkpoint integrity verification failed."
            )

        return checkpoint

    # ========================================================================
    # BLOCKCHAIN VALIDATION
    # ========================================================================

    def validate_blockchain(self) -> bool:
        """
        Validate the complete blockchain.
        """

        if not self.blockchain.chain:
            raise RecoveryIntegrityError(
                "Blockchain contains no blocks."
            )

        try:

            result = (
                self.blockchain.validate_chain()
            )

        except Exception as exc:

            raise RecoveryIntegrityError(
                "Blockchain validation failed with an exception."
            ) from exc

        if isinstance(result, tuple):
            valid = bool(result[0])
        else:
            valid = bool(result)

        if not valid:
            raise RecoveryIntegrityError(
                "Blockchain validation returned failure."
            )

        return True

    # ========================================================================
    # STATE VALIDATION
    # ========================================================================

    def validate_state(
        self,
    ) -> StateEngine:
        """
        Load and verify persistent state.
        """

        try:

            state = self.state_store.load()

        except StateStoreError as exc:

            raise RecoveryIntegrityError(
                "Persistent state verification failed."
            ) from exc

        if not isinstance(
            state,
            StateEngine,
        ):
            raise RecoveryIntegrityError(
                "Persistent storage returned an invalid state object."
            )

        return state

    # ========================================================================
    # CHECKPOINT ↔ BLOCKCHAIN
    # ========================================================================

    def validate_checkpoint_against_chain(
        self,
        checkpoint: RecoveryCheckpoint,
    ) -> bool:
        """
        Verify checkpoint matches blockchain tip.
        """

        checkpoint.validate()

        if not self.blockchain.chain:
            raise RecoveryStateMismatchError(
                "Blockchain is empty."
            )

        latest_block = (
            self.blockchain.chain[-1]
        )

        if (
            checkpoint.block_height
            != latest_block.height
        ):
            raise RecoveryStateMismatchError(
                "Checkpoint height does not match blockchain height."
            )

        if (
            checkpoint.block_hash
            != latest_block.block_hash
        ):
            raise RecoveryStateMismatchError(
                "Checkpoint block hash does not match blockchain tip."
            )

        if (
            checkpoint.previous_block_hash
            != latest_block.previous_hash
        ):
            raise RecoveryStateMismatchError(
                "Checkpoint previous block hash does not match blockchain tip."
            )

        if (
            checkpoint.chain_length
            != len(self.blockchain.chain)
        ):
            raise RecoveryStateMismatchError(
                "Checkpoint chain length does not match blockchain."
            )

        return True

    # ========================================================================
    # CHECKPOINT ↔ STATE
    # ========================================================================

    def validate_state_against_checkpoint(
        self,
        state: StateEngine,
        checkpoint: RecoveryCheckpoint,
    ) -> bool:
        """
        Verify state root and supply against checkpoint.
        """

        actual_root = state.state_root()

        if actual_root != checkpoint.state_root:
            raise RecoveryStateMismatchError(
                "State root does not match recovery checkpoint."
            )

        actual_supply = float(
            state.total_supply
        )

        if abs(
            actual_supply
            - checkpoint.state_supply
        ) > 1e-9:
            raise RecoveryStateMismatchError(
                "State supply does not match recovery checkpoint."
            )

        return True

    # ========================================================================
    # BLOCK ↔ STATE ROOT
    # ========================================================================

    def validate_state_against_block(
        self,
        state: StateEngine,
        block: Block,
    ) -> bool:
        """
        Verify that a block containing a state root
        matches the current state.
        """

        block_state_root = getattr(
            block,
            "state_root",
            "",
        )

        if not block_state_root:
            raise RecoveryStateMismatchError(
                "Block does not contain a state root."
            )

        actual_root = state.state_root()

        if actual_root != block_state_root:
            raise RecoveryStateMismatchError(
                "State root does not match block state root."
            )

        return True

    # ========================================================================
    # FULL VERIFICATION
    # ========================================================================

    def verify_recovery(
        self,
    ) -> dict[str, Any]:
        """
        Perform complete recovery verification.
        """

        self.validate_blockchain()

        state = self.validate_state()

        checkpoint = self.load_checkpoint()

        self.validate_checkpoint_against_chain(
            checkpoint
        )

        self.validate_state_against_checkpoint(
            state,
            checkpoint,
        )

        latest_block = (
            self.blockchain.chain[-1]
        )

        self.validate_state_against_block(
            state,
            latest_block,
        )

        return {
            "valid": True,
            "block_height": checkpoint.block_height,
            "block_hash": checkpoint.block_hash,
            "state_root": checkpoint.state_root,
            "state_supply": checkpoint.state_supply,
            "chain_length": checkpoint.chain_length,
        }

    # ========================================================================
    # RECOVER
    # ========================================================================

    def recover(
        self,
    ) -> StateEngine:
        """
        Recover state after application restart.
        """

        self.validate_blockchain()

        state = self.validate_state()

        checkpoint = self.load_checkpoint()

        self.validate_checkpoint_against_chain(
            checkpoint
        )

        self.validate_state_against_checkpoint(
            state,
            checkpoint,
        )

        latest_block = (
            self.blockchain.chain[-1]
        )

        self.validate_state_against_block(
            state,
            latest_block,
        )

        return state

    # ========================================================================
    # COMMIT RECOVERY POINT
    # ========================================================================

    def commit_recovery_point(
        self,
        state: StateEngine,
    ) -> RecoveryCheckpoint:
        """
        Persist state and create a matching checkpoint.
        """

        self.validate_blockchain()

        persisted_root = (
            self.state_store.save(
                state
            )
        )

        checkpoint = (
            self.create_checkpoint(
                state
            )
        )

        if (
            persisted_root
            != checkpoint.state_root
        ):
            raise RecoveryStateMismatchError(
                "Persisted state root does not match checkpoint."
            )

        latest_block = (
            self.blockchain.chain[-1]
        )

        block_state_root = getattr(
            latest_block,
            "state_root",
            "",
        )

        if block_state_root != checkpoint.state_root:
            raise RecoveryStateMismatchError(
                "Blockchain block state root does not match "
                "persistent state root."
            )

        self.save_checkpoint(
            checkpoint
        )

        return checkpoint

    # ========================================================================
    # STATUS
    # ========================================================================

    def status(self) -> dict[str, Any]:
        """
        Return recovery status.
        """

        result: dict[str, Any] = {
            "recovery_version": RECOVERY_VERSION,
            "checkpoint_exists": (
                self.checkpoint_path.exists()
            ),
            "state_exists": (
                self.state_store.exists()
            ),
            "blockchain_blocks": len(
                self.blockchain.chain
            ),
        }

        if self.blockchain.chain:

            latest = (
                self.blockchain.chain[-1]
            )

            result.update(
                {
                    "latest_height":
                        latest.height,
                    "latest_block_hash":
                        latest.block_hash,
                    "latest_state_root":
                        getattr(
                            latest,
                            "state_root",
                            "",
                        ),
                }
            )

        if self.checkpoint_path.exists():

            try:

                checkpoint = (
                    self.load_checkpoint()
                )

                result.update(
                    {
                        "checkpoint_valid": True,
                        "checkpoint_height":
                            checkpoint.block_height,
                        "checkpoint_hash":
                            checkpoint.block_hash,
                        "checkpoint_state_root":
                            checkpoint.state_root,
                        "checkpoint_supply":
                            checkpoint.state_supply,
                    }
                )

            except RecoveryCheckpointError as exc:

                result.update(
                    {
                        "checkpoint_valid": False,
                        "checkpoint_error": str(exc),
                    }
                )

        return result

    # ========================================================================
    # SELF TEST
    # ========================================================================

    @classmethod
    def self_test(cls) -> None:

        print("=" * 66)
        print(
            "NEXCHAIN BLOCKCHAIN RECOVERY ENGINE TEST"
        )
        print("=" * 66)

        temporary_directory = Path(
            tempfile.mkdtemp(
                prefix="nexchain_recovery_test_"
            )
        )

        state_database = (
            temporary_directory / "state.db"
        )

        checkpoint_file = (
            temporary_directory
            / "checkpoint.json"
        )

        try:

            # ---------------------------------------------------------------
            # 1. BLOCKCHAIN
            # ---------------------------------------------------------------

            validator = (
                "NEX" + ("9" * 40)
            )

            blockchain = Blockchain(
                genesis_validator=validator
            )

            print(
                "[1/10] Blockchain initialized"
            )

            # ---------------------------------------------------------------
            # 2. STATE
            # ---------------------------------------------------------------

            state = StateEngine()

            account_address = (
                "NEX" + ("1" * 40)
            )

            state.accounts[
                account_address
            ] = Account(
                address=account_address,
                balance=1000.0,
                nonce=0,
            )

            state.total_supply = 1000.0

            print(
                "[2/10] State initialized"
            )

            # ---------------------------------------------------------------
            # 3. STORAGE + RECOVERY
            # ---------------------------------------------------------------

            state_store = StateStore(
                state_database
            )

            recovery = cls(
                blockchain=blockchain,
                state_store=state_store,
                checkpoint_path=checkpoint_file,
            )

            print(
                "[3/10] Recovery engine initialized"
            )

            # ---------------------------------------------------------------
            # 4. CREATE BLOCK
            # ---------------------------------------------------------------

            latest_height = (
                blockchain.latest_block.height
            )

            next_height = (
                latest_height + 1
            )

            previous_hash = (
                blockchain.latest_block.block_hash
            )

            block = Block(
                version=1,
                height=next_height,
                previous_hash=previous_hash,
                timestamp=1_700_000_001.0,
                validator=validator,
                nonce=0,
                difficulty=0,
                transactions=[],
                state_root=state.state_root(),
            )

            block.finalize()

            result = blockchain.add_block(
                block
            )

            if isinstance(result, tuple):
                if not result[0]:
                    raise RecoveryError(
                        f"Unable to add test block: {result}"
                    )

            print(
                "[4/10] Blockchain state-root block created"
            )

            # ---------------------------------------------------------------
            # 5. COMMIT RECOVERY POINT
            # ---------------------------------------------------------------

            checkpoint = (
                recovery.commit_recovery_point(
                    state
                )
            )

            assert (
                checkpoint.block_height
                == block.height
            )

            assert (
                checkpoint.block_hash
                == block.block_hash
            )

            assert (
                checkpoint.state_root
                == state.state_root()
            )

            print(
                "[5/10] Recovery checkpoint committed"
            )

            # ---------------------------------------------------------------
            # 6. CHECKPOINT LOAD
            # ---------------------------------------------------------------

            loaded_checkpoint = (
                recovery.load_checkpoint()
            )

            assert (
                loaded_checkpoint
                == checkpoint
            )

            print(
                "[6/10] Checkpoint integrity verified"
            )

            # ---------------------------------------------------------------
            # 7. FULL VERIFICATION
            # ---------------------------------------------------------------

            verification = (
                recovery.verify_recovery()
            )

            assert (
                verification["valid"]
                is True
            )

            assert (
                verification["block_height"]
                == block.height
            )

            assert (
                verification["state_root"]
                == state.state_root()
            )

            print(
                "[7/10] Full recovery verification passed"
            )

            # ---------------------------------------------------------------
            # 8. SIMULATED RESTART
            # ---------------------------------------------------------------

            restarted_store = StateStore(
                state_database
            )

            restarted_recovery = cls(
                blockchain=blockchain,
                state_store=restarted_store,
                checkpoint_path=checkpoint_file,
            )

            recovered_state = (
                restarted_recovery.recover()
            )

            assert (
                recovered_state.state_root()
                == state.state_root()
            )

            assert (
                recovered_state.total_supply
                == 1000.0
            )

            assert (
                recovered_state.accounts[
                    account_address
                ].balance
                == 1000.0
            )

            print(
                "[8/10] Restart recovery passed"
            )

            # ---------------------------------------------------------------
            # 9. STATUS
            # ---------------------------------------------------------------

            status = (
                restarted_recovery.status()
            )

            assert (
                status["checkpoint_exists"]
                is True
            )

            assert (
                status["state_exists"]
                is True
            )

            assert (
                status["blockchain_blocks"]
                == 2
            )

            assert (
                status["latest_state_root"]
                == state.state_root()
            )

            print(
                "[9/10] Recovery status verified"
            )

            # ---------------------------------------------------------------
            # 10. FINAL
            # ---------------------------------------------------------------

            final_result = (
                restarted_recovery.verify_recovery()
            )

            assert (
                final_result["valid"]
                is True
            )

            print(
                "[10/10] Final recovery integrity passed"
            )

            print()
            print("=" * 66)
            print(
                "NEXCHAIN BLOCKCHAIN RECOVERY ENGINE: PASSED"
            )
            print("=" * 66)
            print(
                f"Block Height : "
                f"{checkpoint.block_height}"
            )
            print(
                f"Chain Length : "
                f"{checkpoint.chain_length}"
            )
            print(
                f"Block Hash   : "
                f"{checkpoint.block_hash}"
            )
            print(
                f"State Root   : "
                f"{checkpoint.state_root}"
            )
            print(
                f"State Supply : "
                f"{checkpoint.state_supply}"
            )
            print("=" * 66)

        finally:

            StateStore._safe_delete_database_files(
                state_database
            )

            if checkpoint_file.exists():
                try:
                    checkpoint_file.unlink()
                except OSError:
                    pass

            try:
                temporary_directory.rmdir()
            except OSError:
                pass


# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    RecoveryEngine.self_test()