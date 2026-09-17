"""
NEXCHAIN P2P Node Foundation
============================

Provides the foundation for NEXCHAIN network nodes.

Responsibilities:
    - Node identity
    - Peer registration
    - Peer removal
    - Peer discovery metadata
    - Protocol message construction
    - Message validation
    - Deterministic node identifiers
    - Network statistics

This module intentionally does not open sockets yet.
TCP transport is introduced in the next network phase.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any


# ============================================================
# CONSTANTS
# ============================================================

PROTOCOL_VERSION = 1
NETWORK_NAME = "NEXCHAIN"

NODE_ID_LENGTH = 64
MAX_PEERS = 1000

MESSAGE_TYPES = {
    "handshake",
    "handshake_ack",
    "ping",
    "pong",
    "get_peers",
    "peers",
    "get_blocks",
    "blocks",
    "new_block",
    "new_transaction",
}


# ============================================================
# HELPERS
# ============================================================

def _canonical_json(data: Any) -> str:
    """
    Produce deterministic JSON.
    """

    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )


def _sha256(data: str) -> str:
    """
    Return SHA-256 hexadecimal digest.
    """

    return hashlib.sha256(
        data.encode("utf-8")
    ).hexdigest()


# ============================================================
# NODE IDENTITY
# ============================================================

@dataclass(frozen=True)
class NodeIdentity:
    """
    Immutable identity of a NEXCHAIN network node.
    """

    node_id: str
    address: str
    port: int
    public_key: str = ""

    def __post_init__(self) -> None:

        if not isinstance(self.node_id, str):
            raise ValueError("Node ID must be a string.")

        if len(self.node_id) != NODE_ID_LENGTH:
            raise ValueError("Invalid node ID length.")

        try:
            int(self.node_id, 16)
        except ValueError as exc:
            raise ValueError("Node ID must be hexadecimal.") from exc

        if not isinstance(self.address, str) or not self.address:
            raise ValueError("Node address is required.")

        if not isinstance(self.port, int):
            raise ValueError("Node port must be an integer.")

        if not 1 <= self.port <= 65535:
            raise ValueError("Node port must be between 1 and 65535.")

        if not isinstance(self.public_key, str):
            raise ValueError("Public key must be a string.")

    @classmethod
    def create(
        cls,
        address: str,
        port: int,
        public_key: str = "",
    ) -> "NodeIdentity":
        """
        Create a deterministic node identity.
        """

        identity_payload = {
            "network": NETWORK_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "address": address,
            "port": port,
            "public_key": public_key,
        }

        node_id = _sha256(
            _canonical_json(identity_payload)
        )

        return cls(
            node_id=node_id,
            address=address,
            port=port,
            public_key=public_key,
        )

    def endpoint(self) -> str:
        """
        Return network endpoint.
        """

        return f"{self.address}:{self.port}"

    def to_dict(self) -> dict[str, Any]:
        """
        Serialize node identity.
        """

        return {
            "node_id": self.node_id,
            "address": self.address,
            "port": self.port,
            "public_key": self.public_key,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "NodeIdentity":
        """
        Restore node identity.
        """

        if not isinstance(data, dict):
            raise ValueError("Node identity must be a dictionary.")

        return cls(
            node_id=str(data["node_id"]),
            address=str(data["address"]),
            port=int(data["port"]),
            public_key=str(data.get("public_key", "")),
        )


# ============================================================
# PEER
# ============================================================

@dataclass
class Peer:
    """
    Represents a known network peer.
    """

    identity: NodeIdentity
    first_seen: float = field(default_factory=time.time)
    last_seen: float = field(default_factory=time.time)
    connected: bool = False
    inbound: bool = False
    protocol_version: int = PROTOCOL_VERSION
    blocks_received: int = 0
    blocks_sent: int = 0
    transactions_received: int = 0
    transactions_sent: int = 0

    def mark_seen(self) -> None:
        self.last_seen = time.time()

    def mark_connected(
        self,
        inbound: bool = False,
    ) -> None:
        self.connected = True
        self.inbound = inbound
        self.mark_seen()

    def mark_disconnected(self) -> None:
        self.connected = False
        self.mark_seen()

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "connected": self.connected,
            "inbound": self.inbound,
            "protocol_version": self.protocol_version,
            "blocks_received": self.blocks_received,
            "blocks_sent": self.blocks_sent,
            "transactions_received": self.transactions_received,
            "transactions_sent": self.transactions_sent,
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
    ) -> "Peer":

        identity = NodeIdentity.from_dict(
            data["identity"]
        )

        return cls(
            identity=identity,
            first_seen=float(
                data.get("first_seen", time.time())
            ),
            last_seen=float(
                data.get("last_seen", time.time())
            ),
            connected=bool(
                data.get("connected", False)
            ),
            inbound=bool(
                data.get("inbound", False)
            ),
            protocol_version=int(
                data.get(
                    "protocol_version",
                    PROTOCOL_VERSION,
                )
            ),
            blocks_received=int(
                data.get("blocks_received", 0)
            ),
            blocks_sent=int(
                data.get("blocks_sent", 0)
            ),
            transactions_received=int(
                data.get("transactions_received", 0)
            ),
            transactions_sent=int(
                data.get("transactions_sent", 0)
            ),
        )


# ============================================================
# NETWORK MESSAGE
# ============================================================

@dataclass
class NetworkMessage:
    """
    Canonical NEXCHAIN network protocol message.
    """

    message_type: str
    sender: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)
    protocol_version: int = PROTOCOL_VERSION
    message_id: str = ""

    def __post_init__(self) -> None:

        if self.message_type not in MESSAGE_TYPES:
            raise ValueError(
                f"Unsupported message type: "
                f"{self.message_type}"
            )

        if not isinstance(self.sender, str):
            raise ValueError("Sender must be a string.")

        if len(self.sender) != NODE_ID_LENGTH:
            raise ValueError("Invalid sender node ID.")

        try:
            int(self.sender, 16)
        except ValueError as exc:
            raise ValueError(
                "Sender node ID must be hexadecimal."
            ) from exc

        if not isinstance(self.payload, dict):
            raise ValueError("Payload must be a dictionary.")

        if not isinstance(self.protocol_version, int):
            raise ValueError(
                "Protocol version must be an integer."
            )

        if not self.message_id:
            self.message_id = self.calculate_id()

    def unsigned_payload(self) -> dict[str, Any]:
        return {
            "protocol_version": self.protocol_version,
            "message_type": self.message_type,
            "sender": self.sender,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }

    def calculate_id(self) -> str:
        return _sha256(
            _canonical_json(
                self.unsigned_payload()
            )
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.unsigned_payload(),
            "message_id": self.message_id,
        }

    def encode(self) -> bytes:
        """
        Encode message for future transport layer.
        """

        return (
            _canonical_json(
                self.to_dict()
            ).encode("utf-8")
        )

    @classmethod
    def decode(
        cls,
        data: bytes | str,
    ) -> "NetworkMessage":
        """
        Decode a network message.
        """

        if isinstance(data, bytes):
            data = data.decode("utf-8")

        if not isinstance(data, str):
            raise ValueError(
                "Encoded message must be bytes or string."
            )

        try:
            payload = json.loads(data)
        except json.JSONDecodeError as exc:
            raise ValueError(
                "Invalid network message JSON."
            ) from exc

        if not isinstance(payload, dict):
            raise ValueError(
                "Network message must decode to a dictionary."
            )

        message = cls(
            message_type=payload["message_type"],
            sender=payload["sender"],
            payload=payload.get("payload", {}),
            timestamp=float(
                payload["timestamp"]
            ),
            protocol_version=int(
                payload.get(
                    "protocol_version",
                    PROTOCOL_VERSION,
                )
            ),
            message_id=payload.get(
                "message_id",
                "",
            ),
        )

        expected_id = message.calculate_id()

        if message.message_id != expected_id:
            raise ValueError(
                "Network message integrity check failed."
            )

        return message


# ============================================================
# NODE
# ============================================================

class NetworkNode:
    """
    NEXCHAIN network node foundation.

    Manages:
        - Local node identity
        - Known peers
        - Peer lifecycle
        - Protocol messages
        - Network metadata
    """

    def __init__(
        self,
        address: str,
        port: int,
        public_key: str = "",
        max_peers: int = MAX_PEERS,
    ) -> None:

        if max_peers <= 0:
            raise ValueError(
                "Maximum peers must be positive."
            )

        if max_peers > MAX_PEERS:
            raise ValueError(
                f"Maximum peers cannot exceed {MAX_PEERS}."
            )

        self.identity = NodeIdentity.create(
            address=address,
            port=port,
            public_key=public_key,
        )

        self.max_peers = max_peers

        self.peers: dict[str, Peer] = {}

        self.started_at = time.time()

        self.messages_created = 0
        self.messages_received = 0

    # ========================================================
    # PEER MANAGEMENT
    # ========================================================

    def add_peer(
        self,
        identity: NodeIdentity,
        inbound: bool = False,
    ) -> tuple[bool, str]:
        """
        Register a peer.
        """

        if identity.node_id == self.identity.node_id:
            return False, "Cannot add local node as peer."

        if identity.node_id in self.peers:
            peer = self.peers[identity.node_id]
            peer.mark_seen()
            return False, "Peer already registered."

        if len(self.peers) >= self.max_peers:
            return False, "Peer capacity reached."

        peer = Peer(
            identity=identity,
            inbound=inbound,
        )

        self.peers[identity.node_id] = peer

        return True, "Peer added."

    def remove_peer(
        self,
        node_id: str,
    ) -> tuple[bool, str]:
        """
        Remove a peer.
        """

        if node_id not in self.peers:
            return False, "Peer not found."

        del self.peers[node_id]

        return True, "Peer removed."

    def get_peer(
        self,
        node_id: str,
    ) -> Peer | None:
        return self.peers.get(node_id)

    def mark_peer_connected(
        self,
        node_id: str,
        inbound: bool = False,
    ) -> tuple[bool, str]:

        peer = self.get_peer(node_id)

        if peer is None:
            return False, "Peer not found."

        peer.mark_connected(
            inbound=inbound
        )

        return True, "Peer connected."

    def mark_peer_disconnected(
        self,
        node_id: str,
    ) -> tuple[bool, str]:

        peer = self.get_peer(node_id)

        if peer is None:
            return False, "Peer not found."

        peer.mark_disconnected()

        return True, "Peer disconnected."

    # ========================================================
    # PEER LIST
    # ========================================================

    def connected_peers(self) -> list[Peer]:
        return [
            peer
            for peer in self.peers.values()
            if peer.connected
        ]

    def peer_identities(self) -> list[NodeIdentity]:
        return [
            peer.identity
            for peer in self.peers.values()
        ]

    # ========================================================
    # MESSAGE CREATION
    # ========================================================

    def create_message(
        self,
        message_type: str,
        payload: dict[str, Any] | None = None,
    ) -> NetworkMessage:
        """
        Create a signed-by-identity protocol message.

        Cryptographic node authentication will be added
        when the transport/security layer is introduced.
        """

        message = NetworkMessage(
            message_type=message_type,
            sender=self.identity.node_id,
            payload=payload or {},
        )

        self.messages_created += 1

        return message

    def create_handshake(self) -> NetworkMessage:
        return self.create_message(
            "handshake",
            {
                "network": NETWORK_NAME,
                "protocol_version": PROTOCOL_VERSION,
                "node": self.identity.to_dict(),
            },
        )

    def create_handshake_ack(self) -> NetworkMessage:
        return self.create_message(
            "handshake_ack",
            {
                "network": NETWORK_NAME,
                "protocol_version": PROTOCOL_VERSION,
                "node": self.identity.to_dict(),
            },
        )

    def create_ping(self) -> NetworkMessage:
        return self.create_message(
            "ping",
            {
                "node_id": self.identity.node_id,
                "timestamp": time.time(),
            },
        )

    def create_pong(
        self,
        ping_message_id: str,
    ) -> NetworkMessage:
        return self.create_message(
            "pong",
            {
                "node_id": self.identity.node_id,
                "ping_message_id": ping_message_id,
                "timestamp": time.time(),
            },
        )

    def create_get_peers(self) -> NetworkMessage:
        return self.create_message(
            "get_peers",
            {},
        )

    def create_peers_message(self) -> NetworkMessage:
        return self.create_message(
            "peers",
            {
                "peers": [
                    peer.identity.to_dict()
                    for peer in self.peers.values()
                ],
            },
        )

    # ========================================================
    # MESSAGE PROCESSING
    # ========================================================

    def process_message(
        self,
        message: NetworkMessage,
    ) -> tuple[bool, str]:
        """
        Validate basic protocol compatibility and process
        network metadata.
        """

        if message.protocol_version != PROTOCOL_VERSION:
            return False, "Protocol version mismatch."

        if message.sender == self.identity.node_id:
            return False, "Message originated from local node."

        self.messages_received += 1

        peer = self.get_peer(message.sender)

        if peer is not None:
            peer.mark_seen()

        return True, "Message accepted."

    # ========================================================
    # SERIALIZATION
    # ========================================================

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "max_peers": self.max_peers,
            "started_at": self.started_at,
            "messages_created": self.messages_created,
            "messages_received": self.messages_received,
            "peers": [
                peer.to_dict()
                for peer in self.peers.values()
            ],
        }

    # ========================================================
    # STATISTICS
    # ========================================================

    def stats(self) -> dict[str, Any]:
        connected = len(
            self.connected_peers()
        )

        return {
            "network": NETWORK_NAME,
            "protocol_version": PROTOCOL_VERSION,
            "node_id": self.identity.node_id,
            "endpoint": self.identity.endpoint(),
            "peer_count": len(self.peers),
            "connected_peers": connected,
            "max_peers": self.max_peers,
            "messages_created": self.messages_created,
            "messages_received": self.messages_received,
            "uptime_seconds": max(
                0.0,
                time.time() - self.started_at,
            ),
        }


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 70)
    print("NEXCHAIN NETWORK NODE FOUNDATION TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # Node creation
    # --------------------------------------------------------

    node_a = NetworkNode(
        address="127.0.0.1",
        port=41001,
    )

    node_b = NetworkNode(
        address="127.0.0.1",
        port=41002,
    )

    assert node_a.identity.node_id != node_b.identity.node_id

    print()
    print("[PASS] Node identities created")
    print(
        f"       Node A: {node_a.identity.node_id}"
    )
    print(
        f"       Node B: {node_b.identity.node_id}"
    )

    # --------------------------------------------------------
    # Deterministic identity
    # --------------------------------------------------------

    identity_a_repeat = NodeIdentity.create(
        address="127.0.0.1",
        port=41001,
    )

    assert (
        identity_a_repeat.node_id
        == node_a.identity.node_id
    )

    print("[PASS] Deterministic node identity")

    # --------------------------------------------------------
    # Peer registration
    # --------------------------------------------------------

    added, reason = node_a.add_peer(
        node_b.identity
    )

    assert added, reason

    print("[PASS] Peer registration")

    # --------------------------------------------------------
    # Self-peer protection
    # --------------------------------------------------------

    added, reason = node_a.add_peer(
        node_a.identity
    )

    assert not added

    print("[PASS] Self-peer protection")

    # --------------------------------------------------------
    # Duplicate peer protection
    # --------------------------------------------------------

    added, reason = node_a.add_peer(
        node_b.identity
    )

    assert not added

    print("[PASS] Duplicate peer protection")

    # --------------------------------------------------------
    # Peer connection state
    # --------------------------------------------------------

    connected, reason = node_a.mark_peer_connected(
        node_b.identity.node_id
    )

    assert connected, reason
    assert len(node_a.connected_peers()) == 1

    print("[PASS] Peer connection state")

    # --------------------------------------------------------
    # Handshake
    # --------------------------------------------------------

    handshake = node_a.create_handshake()

    assert handshake.message_type == "handshake"
    assert handshake.sender == node_a.identity.node_id
    assert handshake.message_id

    print("[PASS] Handshake message creation")

    # --------------------------------------------------------
    # Message encoding
    # --------------------------------------------------------

    encoded = handshake.encode()

    assert isinstance(encoded, bytes)
    assert len(encoded) > 0

    print("[PASS] Message encoding")

    # --------------------------------------------------------
    # Message decoding
    # --------------------------------------------------------

    decoded = NetworkMessage.decode(encoded)

    assert decoded.message_id == handshake.message_id
    assert decoded.message_type == "handshake"
    assert decoded.sender == handshake.sender

    print("[PASS] Message decoding")

    # --------------------------------------------------------
    # Message integrity
    # --------------------------------------------------------

    tampered = json.loads(
        encoded.decode("utf-8")
    )

    tampered["payload"]["network"] = "INVALID"

    tampered_bytes = _canonical_json(
        tampered
    ).encode("utf-8")

    try:
        NetworkMessage.decode(
            tampered_bytes
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "Tampered message was accepted."
        )

    print("[PASS] Message integrity protection")

    # --------------------------------------------------------
    # Message processing
    # --------------------------------------------------------

    accepted, reason = node_b.process_message(
        handshake
    )

    assert accepted, reason

    print("[PASS] Message processing")

    # --------------------------------------------------------
    # Ping / pong
    # --------------------------------------------------------

    ping = node_a.create_ping()

    assert ping.message_type == "ping"

    pong = node_b.create_pong(
        ping.message_id
    )

    assert pong.message_type == "pong"
    assert (
        pong.payload["ping_message_id"]
        == ping.message_id
    )

    print("[PASS] Ping / pong protocol")

    # --------------------------------------------------------
    # Peer list
    # --------------------------------------------------------

    peers_message = node_a.create_peers_message()

    assert peers_message.message_type == "peers"
    assert len(
        peers_message.payload["peers"]
    ) == 1

    print("[PASS] Peer discovery message")

    # --------------------------------------------------------
    # Peer serialization
    # --------------------------------------------------------

    peer = node_a.get_peer(
        node_b.identity.node_id
    )

    assert peer is not None

    peer_copy = Peer.from_dict(
        peer.to_dict()
    )

    assert (
        peer_copy.identity.node_id
        == peer.identity.node_id
    )

    print("[PASS] Peer serialization")

    # --------------------------------------------------------
    # Peer removal
    # --------------------------------------------------------

    removed, reason = node_a.remove_peer(
        node_b.identity.node_id
    )

    assert removed, reason
    assert (
        node_a.get_peer(
            node_b.identity.node_id
        )
        is None
    )

    print("[PASS] Peer removal")

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    stats = node_a.stats()

    assert stats["network"] == NETWORK_NAME
    assert stats["protocol_version"] == PROTOCOL_VERSION
    assert stats["peer_count"] == 0

    print("[PASS] Network statistics")

    # --------------------------------------------------------
    # Final
    # --------------------------------------------------------

    print()
    print("Node statistics:")
    print(node_a.stats())

    print()
    print("=" * 70)
    print("ALL NETWORK FOUNDATION TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()