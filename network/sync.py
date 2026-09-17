"""
NEXCHAIN Blockchain Synchronization
===================================

Connects the NEXCHAIN blockchain engine to the TCP P2P
transport layer.

Responsibilities:
    - Request remote blockchain blocks
    - Serve local blockchain blocks
    - Validate received blocks
    - Sequentially append synchronized blocks
    - Detect divergent chains
    - Track synchronization state
    - Prevent duplicate blocks
    - Provide synchronization statistics
"""

from __future__ import annotations

import threading
import time
from typing import Any

from core.block import Block
from core.blockchain import Blockchain
from network.node import NetworkMessage
from network.transport import (
    PeerConnection,
    TCPTransport,
)


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_BATCH_SIZE = 50
MAX_BATCH_SIZE = 500

SYNC_REQUEST = "get_blocks"
SYNC_RESPONSE = "blocks"


# ============================================================
# ERRORS
# ============================================================

class SyncError(Exception):
    """Base synchronization error."""


class ChainDivergenceError(SyncError):
    """Raised when two chains disagree at the same height."""


class InvalidBlockBatchError(SyncError):
    """Raised when a received block batch is invalid."""


# ============================================================
# SYNCHRONIZATION STATE
# ============================================================

class SyncState:
    """
    Runtime synchronization state.
    """

    def __init__(self) -> None:

        self.syncing = False
        self.target_height = 0
        self.start_height = 0
        self.current_height = 0

        self.blocks_requested = 0
        self.blocks_received = 0
        self.blocks_added = 0
        self.blocks_skipped = 0

        self.requests_sent = 0
        self.responses_sent = 0

        self.last_sync_started = 0.0
        self.last_sync_completed = 0.0
        self.last_error = ""

        self._lock = threading.RLock()

    def begin(
        self,
        start_height: int,
        target_height: int,
    ) -> None:

        with self._lock:

            self.syncing = True
            self.start_height = start_height
            self.target_height = target_height
            self.current_height = start_height - 1

            self.blocks_requested = 0
            self.blocks_received = 0
            self.blocks_added = 0
            self.blocks_skipped = 0

            self.requests_sent = 0
            self.responses_sent = 0

            self.last_error = ""
            self.last_sync_started = time.time()

    def complete(
        self,
        current_height: int,
    ) -> None:

        with self._lock:

            self.syncing = False
            self.current_height = current_height
            self.last_sync_completed = time.time()

    def fail(
        self,
        error: str,
        current_height: int,
    ) -> None:

        with self._lock:

            self.syncing = False
            self.current_height = current_height
            self.last_error = error

    def to_dict(self) -> dict[str, Any]:

        with self._lock:

            return {
                "syncing": self.syncing,
                "target_height": self.target_height,
                "start_height": self.start_height,
                "current_height": self.current_height,
                "blocks_requested": self.blocks_requested,
                "blocks_received": self.blocks_received,
                "blocks_added": self.blocks_added,
                "blocks_skipped": self.blocks_skipped,
                "requests_sent": self.requests_sent,
                "responses_sent": self.responses_sent,
                "last_sync_started": self.last_sync_started,
                "last_sync_completed": self.last_sync_completed,
                "last_error": self.last_error,
            }


# ============================================================
# BLOCKCHAIN SYNCHRONIZER
# ============================================================

class BlockchainSynchronizer:
    """
    Synchronizes one local Blockchain with connected peers.
    """

    def __init__(
        self,
        blockchain: Blockchain,
        transport: TCPTransport,
        batch_size: int = DEFAULT_BATCH_SIZE,
    ) -> None:

        if batch_size <= 0:
            raise ValueError(
                "Batch size must be positive."
            )

        if batch_size > MAX_BATCH_SIZE:
            raise ValueError(
                f"Batch size cannot exceed {MAX_BATCH_SIZE}."
            )

        self.blockchain = blockchain
        self.transport = transport
        self.batch_size = batch_size

        self.state = SyncState()

        self._sync_lock = threading.RLock()

    # ========================================================
    # CHAIN INFORMATION
    # ========================================================

    @property
    def height(self) -> int:
        return self.blockchain.height

    def chain_summary(self) -> dict[str, Any]:

        return {
            "height": self.blockchain.height,
            "latest_hash": (
                self.blockchain.latest_block.block_hash
            ),
            "blocks": len(
                self.blockchain.chain
            ),
        }

    # ========================================================
    # BLOCK SERIALIZATION
    # ========================================================

    @staticmethod
    def serialize_blocks(
        blocks: list[Block],
    ) -> list[dict[str, Any]]:

        return [
            block.to_dict()
            for block in blocks
        ]

    @staticmethod
    def deserialize_blocks(
        data: list[dict[str, Any]],
    ) -> list[Block]:

        if not isinstance(data, list):
            raise InvalidBlockBatchError(
                "Block payload must be a list."
            )

        blocks: list[Block] = []

        for item in data:

            if not isinstance(item, dict):
                raise InvalidBlockBatchError(
                    "Every block must be an object."
                )

            try:
                block = Block.from_dict(item)
            except (
                KeyError,
                TypeError,
                ValueError,
            ) as exc:
                raise InvalidBlockBatchError(
                    f"Invalid block serialization: {exc}"
                ) from exc

            blocks.append(block)

        return blocks

    # ========================================================
    # REQUEST CREATION
    # ========================================================

    def create_request(
        self,
        start_height: int,
        max_blocks: int | None = None,
    ) -> NetworkMessage:

        if start_height < 0:
            raise ValueError(
                "Start height cannot be negative."
            )

        count = (
            max_blocks
            if max_blocks is not None
            else self.batch_size
        )

        if count <= 0 or count > MAX_BATCH_SIZE:
            raise ValueError(
                "Invalid synchronization batch size."
            )

        return self.transport.node.create_message(
            SYNC_REQUEST,
            {
                "start_height": start_height,
                "max_blocks": count,
                "local_height": self.blockchain.height,
                "local_latest_hash": (
                    self.blockchain.latest_block.block_hash
                ),
            },
        )

    # ========================================================
    # REQUEST HANDLING
    # ========================================================

    def handle_get_blocks(
        self,
        message: NetworkMessage,
        connection: PeerConnection,
    ) -> None:
        """
        Serve a block range to a peer.
        """

        payload = message.payload

        try:

            start_height = int(
                payload["start_height"]
            )

            max_blocks = int(
                payload.get(
                    "max_blocks",
                    self.batch_size,
                )
            )

        except (
            KeyError,
            TypeError,
            ValueError,
        ):

            return

        if start_height < 0:
            return

        if (
            max_blocks <= 0
            or max_blocks > MAX_BATCH_SIZE
        ):
            return

        if start_height > self.blockchain.height:
            blocks: list[Block] = []

        else:

            end_height = min(
                start_height + max_blocks,
                self.blockchain.height + 1,
            )

            blocks = self.blockchain.chain[
                start_height:end_height
            ]

        response = self.transport.node.create_message(
            SYNC_RESPONSE,
            {
                "start_height": start_height,
                "blocks": self.serialize_blocks(
                    blocks
                ),
                "source_height": (
                    self.blockchain.height
                ),
                "source_latest_hash": (
                    self.blockchain.latest_block.block_hash
                ),
            },
        )

        sent, _reason = self.transport.send(
            connection.identity.node_id,
            response,
        )

        if sent:

            self.state.responses_sent += 1

    # ========================================================
    # PEER SYNC REQUEST
    # ========================================================

    def request_sync(
        self,
        node_id: str,
    ) -> tuple[bool, str]:

        with self._sync_lock:

            if not self.transport.is_connected(
                node_id
            ):
                return False, "Peer is not connected."

            request = self.create_request(
                start_height=self.blockchain.height + 1
            )

            sent, reason = self.transport.send(
                node_id,
                request,
            )

            if not sent:
                return False, reason

            self.state.requests_sent += 1
            self.state.blocks_requested += (
                self.batch_size
            )

            return True, "Synchronization requested."

    # ========================================================
    # PROCESS BLOCK RESPONSE
    # ========================================================

    def handle_blocks(
        self,
        message: NetworkMessage,
        connection: PeerConnection,
    ) -> tuple[bool, str]:

        with self._sync_lock:

            try:

                start_height = int(
                    message.payload[
                        "start_height"
                    ]
                )

                blocks = self.deserialize_blocks(
                    message.payload[
                        "blocks"
                    ]
                )

            except (
                KeyError,
                TypeError,
                ValueError,
                InvalidBlockBatchError,
            ) as exc:

                self.state.fail(
                    str(exc),
                    self.blockchain.height,
                )

                return False, str(exc)

            self.state.blocks_received += len(
                blocks
            )

            if not blocks:

                self.state.complete(
                    self.blockchain.height
                )

                return True, "No new blocks."

            expected_height = start_height

            for block in blocks:

                if block.height != expected_height:

                    error = (
                        "Non-sequential block batch."
                    )

                    self.state.fail(
                        error,
                        self.blockchain.height,
                    )

                    return False, error

                expected_height += 1

            for block in blocks:

                result = self._apply_block(
                    block
                )

                if result == "added":
                    self.state.blocks_added += 1

                elif result == "skipped":
                    self.state.blocks_skipped += 1

                else:

                    self.state.fail(
                        result,
                        self.blockchain.height,
                    )

                    return False, result

            if (
                blocks[-1].height
                >= self.blockchain.height
            ):

                self.state.current_height = (
                    self.blockchain.height
                )

            return True, "Blocks processed."

    # ========================================================
    # APPLY BLOCK
    # ========================================================

    def _apply_block(
        self,
        block: Block,
    ) -> str:
        """
        Apply one remotely received block.

        Existing identical blocks are harmless and skipped.
        A conflicting block is rejected.
        """

        local_height = self.blockchain.height

        # ----------------------------------------------------
        # Existing height
        # ----------------------------------------------------

        if block.height <= local_height:

            local_block = self.blockchain.chain[
                block.height
            ]

            if (
                local_block.block_hash
                == block.block_hash
            ):
                return "skipped"

            raise ChainDivergenceError(
                f"Chain divergence at height "
                f"{block.height}."
            )

        # ----------------------------------------------------
        # Future gap
        # ----------------------------------------------------

        expected_height = local_height + 1

        if block.height != expected_height:

            return (
                f"Block height gap. Expected "
                f"{expected_height}, received "
                f"{block.height}."
            )

        # ----------------------------------------------------
        # Append through canonical blockchain API
        # ----------------------------------------------------

        added, reason = self.blockchain.add_block(
            block
        )

        if not added:
            return reason

        return "added"

    # ========================================================
    # FULL SYNCHRONIZATION
    # ========================================================

    def synchronize_from_peer(
        self,
        node_id: str,
        target_height: int | None = None,
    ) -> tuple[bool, str]:

        with self._sync_lock:

            if not self.transport.is_connected(
                node_id
            ):
                return False, "Peer is not connected."

            peer = self.node_peer(
                node_id
            )

            if peer is None:
                return False, "Peer not registered."

            self.state.begin(
                start_height=(
                    self.blockchain.height + 1
                ),
                target_height=(
                    target_height
                    if target_height is not None
                    else self.blockchain.height
                ),
            )

            request = self.create_request(
                start_height=(
                    self.blockchain.height + 1
                )
            )

            sent, reason = self.transport.send(
                node_id,
                request,
            )

            if not sent:

                self.state.fail(
                    reason,
                    self.blockchain.height,
                )

                return False, reason

            self.state.requests_sent += 1

            return True, "Synchronization started."

    # ========================================================
    # PEER LOOKUP
    # ========================================================

    def node_peer(
        self,
        node_id: str,
    ):

        return self.transport.node.get_peer(
            node_id
        )

    # ========================================================
    # MESSAGE HANDLER
    # ========================================================

    def handle_message(
        self,
        message: NetworkMessage,
        connection: PeerConnection,
    ) -> None:
        """
        Attach this method to TCPTransport as the application
        message handler.
        """

        if message.message_type == SYNC_REQUEST:

            self.handle_get_blocks(
                message,
                connection,
            )

        elif message.message_type == SYNC_RESPONSE:

            accepted, _reason = self.handle_blocks(
                message,
                connection,
            )

            if not accepted:
                return

            # If the remote peer still has more blocks,
            # request the next batch.
            source_height = int(
                message.payload.get(
                    "source_height",
                    self.blockchain.height,
                )
            )

            if (
                self.blockchain.height
                < source_height
            ):

                next_request = self.create_request(
                    start_height=(
                        self.blockchain.height + 1
                    )
                )

                sent, _reason = self.transport.send(
                    connection.identity.node_id,
                    next_request,
                )

                if sent:
                    self.state.requests_sent += 1

            else:

                self.state.complete(
                    self.blockchain.height
                )

    # ========================================================
    # STATUS
    # ========================================================

    def stats(self) -> dict[str, Any]:

        result = self.state.to_dict()

        result.update(
            {
                "local_height": (
                    self.blockchain.height
                ),
                "local_latest_hash": (
                    self.blockchain.latest_block.block_hash
                ),
                "connected_peers": len(
                    self.transport.connected_node_ids()
                ),
                "batch_size": self.batch_size,
            }
        )

        return result


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 70)
    print("NEXCHAIN BLOCKCHAIN SYNCHRONIZATION TEST")
    print("=" * 70)

    from crypto.crypto_engine import Wallet

    # --------------------------------------------------------
    # Validators
    # --------------------------------------------------------

    validator_a = Wallet.generate()
    validator_b = Wallet.generate()

    # --------------------------------------------------------
    # Source blockchain
    # --------------------------------------------------------

    source_chain = Blockchain(
        genesis_validator=validator_a.address()
    )

    # Create three blocks on source.
    for _ in range(3):

        block = source_chain.create_next_block(
            validator=validator_a.address(),
            transactions=[],
        )

        added, reason = source_chain.add_block(
            block
        )

        assert added, reason

    assert source_chain.height == 3

    print("[PASS] Source blockchain created")

    # --------------------------------------------------------
    # Target blockchain
    # --------------------------------------------------------

    target_chain = Blockchain(
        genesis_validator=validator_a.address()
    )

    assert target_chain.height == 0

    print("[PASS] Target blockchain initialized")

    # --------------------------------------------------------
    # Transport nodes
    # --------------------------------------------------------

    node_a = __import__(
        "network.node",
        fromlist=["NetworkNode"],
    ).NetworkNode(
        address="127.0.0.1",
        port=41021,
    )

    node_b = __import__(
        "network.node",
        fromlist=["NetworkNode"],
    ).NetworkNode(
        address="127.0.0.1",
        port=41022,
    )

    transport_a = TCPTransport(
        node=node_a,
        host="127.0.0.1",
        port=41021,
    )

    transport_b = TCPTransport(
        node=node_b,
        host="127.0.0.1",
        port=41022,
    )

    sync_a = BlockchainSynchronizer(
        blockchain=source_chain,
        transport=transport_a,
    )

    sync_b = BlockchainSynchronizer(
        blockchain=target_chain,
        transport=transport_b,
    )

    transport_a.message_handler = (
        sync_a.handle_message
    )

    transport_b.message_handler = (
        sync_b.handle_message
    )

    try:

        # ----------------------------------------------------
        # Start servers
        # ----------------------------------------------------

        transport_a.start()
        transport_b.start()

        print("[PASS] Synchronization servers started")

        # ----------------------------------------------------
        # Connect
        # ----------------------------------------------------

        connected, reason = transport_b.connect(
            "127.0.0.1",
            41021,
        )

        assert connected, reason

        deadline = time.time() + 3.0

        while time.time() < deadline:

            if (
                transport_b.is_connected(
                    node_a.identity.node_id
                )
                and transport_a.is_connected(
                    node_b.identity.node_id
                )
            ):
                break

            time.sleep(0.05)

        assert transport_b.is_connected(
            node_a.identity.node_id
        )

        print("[PASS] Synchronization peers connected")

        # ----------------------------------------------------
        # Request blocks
        # ----------------------------------------------------

        sent, reason = sync_b.request_sync(
            node_a.identity.node_id
        )

        assert sent, reason

        print("[PASS] Synchronization request sent")

        # ----------------------------------------------------
        # Wait for synchronization
        # ----------------------------------------------------

        deadline = time.time() + 5.0

        while time.time() < deadline:

            if target_chain.height == source_chain.height:
                break

            time.sleep(0.05)

        assert (
            target_chain.height
            == source_chain.height
        )

        print("[PASS] Blockchain synchronized")

        # ----------------------------------------------------
        # Compare hashes
        # ----------------------------------------------------

        assert (
            target_chain.latest_block.block_hash
            == source_chain.latest_block.block_hash
        )

        print("[PASS] Latest block hash synchronized")

        # ----------------------------------------------------
        # Validate target
        # ----------------------------------------------------

        valid, reason = (
            target_chain.validate_chain()
        )

        assert valid, reason

        print("[PASS] Synchronized chain validated")

        # ----------------------------------------------------
        # Compare every block
        # ----------------------------------------------------

        assert len(
            target_chain.chain
        ) == len(
            source_chain.chain
        )

        for source, target in zip(
            source_chain.chain,
            target_chain.chain,
        ):

            assert (
                source.block_hash
                == target.block_hash
            )

        print("[PASS] Complete chain equality")

        # ----------------------------------------------------
        # Duplicate handling
        # ----------------------------------------------------

        duplicate = source_chain.chain[1]

        result = sync_b._apply_block(
            duplicate
        )

        assert result == "skipped"

        print("[PASS] Duplicate block protection")

        # ----------------------------------------------------
        # Statistics
        # ----------------------------------------------------

        stats = sync_b.stats()

        assert (
            stats["local_height"]
            == source_chain.height
        )

        print("[PASS] Synchronization statistics")

    finally:

        transport_a.stop()
        transport_b.stop()

    print()
    print("Synchronization statistics:")
    print(sync_b.stats())

    print()
    print("=" * 70)
    print("ALL BLOCKCHAIN SYNCHRONIZATION TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()