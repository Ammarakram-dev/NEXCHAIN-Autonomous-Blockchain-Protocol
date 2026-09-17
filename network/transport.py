"""
NEXCHAIN TCP P2P Transport
==========================

Provides real TCP networking for NEXCHAIN nodes.

Responsibilities:
    - TCP server
    - TCP client connections
    - Length-prefixed protocol frames
    - Handshake exchange
    - Ping/Pong
    - Thread-safe peer connections
    - Receive loops
    - Graceful disconnection

The transport layer depends on network.node but does not
modify blockchain, consensus, state, or storage logic.
"""

from __future__ import annotations

import socket
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable

from network.node import (
    NETWORK_NAME,
    PROTOCOL_VERSION,
    NetworkMessage,
    NetworkNode,
    NodeIdentity,
)


# ============================================================
# CONSTANTS
# ============================================================

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 41000

MAX_FRAME_SIZE = 4 * 1024 * 1024
HEADER_SIZE = 4

SOCKET_TIMEOUT = 5.0
ACCEPT_TIMEOUT = 1.0


# ============================================================
# ERRORS
# ============================================================

class TransportError(Exception):
    """Base transport error."""


class FrameError(TransportError):
    """Raised when a network frame is invalid."""


class ConnectionClosed(TransportError):
    """Raised when a peer closes the connection."""


# ============================================================
# FRAME CODEC
# ============================================================

class FrameCodec:
    """
    Converts NetworkMessage objects into TCP-safe frames.

    Frame format:

        [4-byte unsigned big-endian length][JSON payload]

    The length prefix prevents message-boundary ambiguity
    when using a TCP byte stream.
    """

    @staticmethod
    def encode(message: NetworkMessage) -> bytes:
        payload = message.encode()

        if len(payload) > MAX_FRAME_SIZE:
            raise FrameError(
                "Network message exceeds maximum frame size."
            )

        header = struct.pack(
            "!I",
            len(payload),
        )

        return header + payload

    @staticmethod
    def decode_frame(frame: bytes) -> NetworkMessage:
        if len(frame) < HEADER_SIZE:
            raise FrameError("Incomplete frame header.")

        payload_length = struct.unpack(
            "!I",
            frame[:HEADER_SIZE],
        )[0]

        if payload_length <= 0:
            raise FrameError("Invalid frame payload length.")

        if payload_length > MAX_FRAME_SIZE:
            raise FrameError(
                "Frame exceeds maximum allowed size."
            )

        expected_size = HEADER_SIZE + payload_length

        if len(frame) != expected_size:
            raise FrameError(
                "Frame size does not match payload length."
            )

        payload = frame[HEADER_SIZE:]

        return NetworkMessage.decode(payload)


# ============================================================
# SOCKET HELPERS
# ============================================================

def _recv_exact(
    connection: socket.socket,
    size: int,
) -> bytes:
    """
    Receive exactly `size` bytes.
    """

    chunks: list[bytes] = []
    remaining = size

    while remaining > 0:

        chunk = connection.recv(remaining)

        if not chunk:
            raise ConnectionClosed(
                "Peer closed the connection."
            )

        chunks.append(chunk)
        remaining -= len(chunk)

    return b"".join(chunks)


def _receive_message(
    connection: socket.socket,
) -> NetworkMessage:
    """
    Receive one complete length-prefixed message.
    """

    header = _recv_exact(
        connection,
        HEADER_SIZE,
    )

    payload_length = struct.unpack(
        "!I",
        header,
    )[0]

    if payload_length <= 0:
        raise FrameError(
            "Invalid message payload length."
        )

    if payload_length > MAX_FRAME_SIZE:
        raise FrameError(
            "Incoming frame exceeds maximum size."
        )

    payload = _recv_exact(
        connection,
        payload_length,
    )

    return NetworkMessage.decode(payload)


def _send_message(
    connection: socket.socket,
    message: NetworkMessage,
) -> None:
    """
    Send one complete framed message.
    """

    frame = FrameCodec.encode(message)

    connection.sendall(frame)


# ============================================================
# CONNECTION
# ============================================================

@dataclass
class PeerConnection:
    """
    Represents one active TCP connection.
    """

    identity: NodeIdentity
    socket: socket.socket
    address: str
    port: int
    inbound: bool
    connected_at: float
    send_lock: threading.Lock

    def send(
        self,
        message: NetworkMessage,
    ) -> None:

        with self.send_lock:
            _send_message(
                self.socket,
                message,
            )

    def close(self) -> None:

        try:
            self.socket.shutdown(
                socket.SHUT_RDWR
            )
        except OSError:
            pass

        try:
            self.socket.close()
        except OSError:
            pass


# ============================================================
# TCP TRANSPORT
# ============================================================

class TCPTransport:
    """
    Real TCP transport for a NEXCHAIN NetworkNode.

    One listener accepts inbound connections.

    Each active connection receives messages on its own
    daemon thread. Sending is protected by a per-connection
    lock so concurrent sends cannot corrupt frames.
    """

    def __init__(
        self,
        node: NetworkNode,
        host: str | None = None,
        port: int | None = None,
        message_handler: Callable[
            [NetworkMessage, PeerConnection],
            None,
        ] | None = None,
    ) -> None:

        self.node = node

        self.host = host or node.identity.address
        self.port = port or node.identity.port

        if not 1 <= self.port <= 65535:
            raise ValueError(
                "TCP port must be between 1 and 65535."
            )

        self.message_handler = message_handler

        self._server_socket: socket.socket | None = None

        self._connections: dict[
            str,
            PeerConnection,
        ] = {}

        self._connections_lock = threading.RLock()

        self._running = False

        self._accept_thread: threading.Thread | None = None

        self._receive_threads: dict[
            str,
            threading.Thread,
        ] = {}

        self.messages_sent = 0
        self.messages_received = 0
        self.connection_attempts = 0
        self.connection_failures = 0

    # ========================================================
    # SERVER
    # ========================================================

    def start(self) -> None:
        """
        Start the TCP listener.
        """

        if self._running:
            return

        server = socket.socket(
            socket.AF_INET,
            socket.SOCK_STREAM,
        )

        server.setsockopt(
            socket.SOL_SOCKET,
            socket.SO_REUSEADDR,
            1,
        )

        server.bind(
            (self.host, self.port)
        )

        server.listen(
            self.node.max_peers
        )

        server.settimeout(
            ACCEPT_TIMEOUT
        )

        self._server_socket = server
        self._running = True

        self._accept_thread = threading.Thread(
            target=self._accept_loop,
            name=f"nexchain-accept-{self.port}",
            daemon=True,
        )

        self._accept_thread.start()

    def _accept_loop(self) -> None:

        while self._running:

            server = self._server_socket

            if server is None:
                break

            try:
                connection, address = server.accept()

            except socket.timeout:
                continue

            except OSError:

                if self._running:
                    continue

                break

            connection.settimeout(
                SOCKET_TIMEOUT
            )

            thread = threading.Thread(
                target=self._handle_inbound,
                args=(connection, address),
                name=f"nexchain-inbound-{address}",
                daemon=True,
            )

            thread.start()

    # ========================================================
    # INBOUND CONNECTION
    # ========================================================

    def _handle_inbound(
        self,
        connection: socket.socket,
        address: tuple[str, int],
    ) -> None:

        try:

            handshake = _receive_message(
                connection
            )

            if handshake.message_type != "handshake":
                raise TransportError(
                    "First message must be handshake."
                )

            if not self._validate_handshake(
                handshake
            ):
                raise TransportError(
                    "Invalid handshake."
                )

            identity = NodeIdentity.from_dict(
                handshake.payload["node"]
            )

            if identity.node_id == self.node.identity.node_id:
                raise TransportError(
                    "Self-connection rejected."
                )

            added, reason = self.node.add_peer(
                identity,
                inbound=True,
            )

            if not added and reason != "Peer already registered.":
                raise TransportError(reason)

            connection_info = PeerConnection(
                identity=identity,
                socket=connection,
                address=address[0],
                port=address[1],
                inbound=True,
                connected_at=time.time(),
                send_lock=threading.Lock(),
            )

            self._register_connection(
                connection_info
            )

            self.node.mark_peer_connected(
                identity.node_id,
                inbound=True,
            )

            connection_info.send(
                self.node.create_handshake_ack()
            )

            self._receive_loop(
                connection_info
            )

        except (
            OSError,
            ValueError,
            KeyError,
            TransportError,
            ConnectionClosed,
        ):
            try:
                connection.close()
            except OSError:
                pass

    # ========================================================
    # OUTBOUND CONNECTION
    # ========================================================

    def connect(
        self,
        address: str,
        port: int,
        timeout: float = SOCKET_TIMEOUT,
    ) -> tuple[bool, str]:
        """
        Connect to another NEXCHAIN node.
        """

        if not 1 <= port <= 65535:
            return False, "Invalid peer port."

        if (
            address == self.host
            and port == self.port
        ):
            return False, "Cannot connect to local node."

        self.connection_attempts += 1

        connection: socket.socket | None = None

        try:

            connection = socket.socket(
                socket.AF_INET,
                socket.SOCK_STREAM,
            )

            connection.settimeout(
                timeout
            )

            connection.connect(
                (address, port)
            )

            connection.settimeout(
                SOCKET_TIMEOUT
            )

            connection.sendall(
                FrameCodec.encode(
                    self.node.create_handshake()
                )
            )

            response = _receive_message(
                connection
            )

            if response.message_type != "handshake_ack":
                raise TransportError(
                    "Expected handshake acknowledgement."
                )

            if not self._validate_handshake(
                response
            ):
                raise TransportError(
                    "Invalid handshake acknowledgement."
                )

            identity = NodeIdentity.from_dict(
                response.payload["node"]
            )

            if identity.node_id == self.node.identity.node_id:
                raise TransportError(
                    "Remote node returned local identity."
                )

            added, reason = self.node.add_peer(
                identity,
                inbound=False,
            )

            if (
                not added
                and reason != "Peer already registered."
            ):
                raise TransportError(reason)

            connection_info = PeerConnection(
                identity=identity,
                socket=connection,
                address=address,
                port=port,
                inbound=False,
                connected_at=time.time(),
                send_lock=threading.Lock(),
            )

            self._register_connection(
                connection_info
            )

            self.node.mark_peer_connected(
                identity.node_id,
                inbound=False,
            )

            receive_thread = threading.Thread(
                target=self._receive_loop,
                args=(connection_info,),
                name=f"nexchain-outbound-{port}",
                daemon=True,
            )

            self._receive_threads[
                identity.node_id
            ] = receive_thread

            receive_thread.start()

            return True, "Connected."

        except (
            OSError,
            ValueError,
            KeyError,
            TransportError,
            ConnectionClosed,
        ) as exc:

            self.connection_failures += 1

            if connection is not None:

                try:
                    connection.close()
                except OSError:
                    pass

            return False, str(exc)

    # ========================================================
    # HANDSHAKE
    # ========================================================

    @staticmethod
    def _validate_handshake(
        message: NetworkMessage,
    ) -> bool:

        if message.protocol_version != PROTOCOL_VERSION:
            return False

        if message.payload.get(
            "network"
        ) != NETWORK_NAME:
            return False

        if int(
            message.payload.get(
                "protocol_version",
                -1,
            )
        ) != PROTOCOL_VERSION:
            return False

        node_data = message.payload.get(
            "node"
        )

        if not isinstance(
            node_data,
            dict,
        ):
            return False

        try:

            identity = NodeIdentity.from_dict(
                node_data
            )

        except (
            KeyError,
            ValueError,
            TypeError,
        ):
            return False

        return (
            identity.node_id
            == message.sender
        )

    # ========================================================
    # CONNECTION REGISTRY
    # ========================================================

    def _register_connection(
        self,
        connection: PeerConnection,
    ) -> None:

        old_connection: PeerConnection | None = None

        with self._connections_lock:

            old_connection = self._connections.get(
                connection.identity.node_id
            )

            self._connections[
                connection.identity.node_id
            ] = connection

        if (
            old_connection is not None
            and old_connection is not connection
        ):
            old_connection.close()

    def _remove_connection(
        self,
        node_id: str,
        connection: PeerConnection,
    ) -> None:

        with self._connections_lock:

            current = self._connections.get(
                node_id
            )

            if current is connection:
                del self._connections[
                    node_id
                ]

    # ========================================================
    # RECEIVE LOOP
    # ========================================================

    def _receive_loop(
        self,
        connection: PeerConnection,
    ) -> None:

        try:

            while self._running:

                message = _receive_message(
                    connection.socket
                )

                self.messages_received += 1

                accepted, _reason = (
                    self.node.process_message(
                        message
                    )
                )

                if not accepted:
                    continue

                self._handle_protocol_message(
                    message,
                    connection,
                )

                if self.message_handler is not None:

                    try:
                        self.message_handler(
                            message,
                            connection,
                        )
                    except Exception:
                        # Application-level handlers must not
                        # terminate the network receive loop.
                        pass

        except (
            OSError,
            ConnectionClosed,
            FrameError,
            ValueError,
        ):
            pass

        finally:

            self._remove_connection(
                connection.identity.node_id,
                connection,
            )

            self.node.mark_peer_disconnected(
                connection.identity.node_id
            )

            connection.close()

    # ========================================================
    # PROTOCOL HANDLING
    # ========================================================

    def _handle_protocol_message(
        self,
        message: NetworkMessage,
        connection: PeerConnection,
    ) -> None:

        if message.message_type == "ping":

            pong = self.node.create_pong(
                message.message_id
            )

            self.send(
                connection.identity.node_id,
                pong,
            )

        elif message.message_type == "get_peers":

            peers_message = (
                self.node.create_peers_message()
            )

            self.send(
                connection.identity.node_id,
                peers_message,
            )

        elif message.message_type == "pong":

            peer = self.node.get_peer(
                connection.identity.node_id
            )

            if peer is not None:
                peer.mark_seen()

    # ========================================================
    # SEND
    # ========================================================

    def send(
        self,
        node_id: str,
        message: NetworkMessage,
    ) -> tuple[bool, str]:

        with self._connections_lock:

            connection = self._connections.get(
                node_id
            )

        if connection is None:
            return False, "Peer is not connected."

        try:

            connection.send(
                message
            )

            self.messages_sent += 1

            return True, "Message sent."

        except OSError as exc:

            return False, str(exc)

    def broadcast(
        self,
        message: NetworkMessage,
        exclude_node_id: str | None = None,
    ) -> int:
        """
        Broadcast a message to all active peers.

        Returns number of successful sends.
        """

        with self._connections_lock:

            connections = list(
                self._connections.values()
            )

        successful = 0

        for connection in connections:

            if (
                exclude_node_id is not None
                and connection.identity.node_id
                == exclude_node_id
            ):
                continue

            try:

                connection.send(
                    message
                )

                self.messages_sent += 1
                successful += 1

            except OSError:
                pass

        return successful

    # ========================================================
    # CONNECTION QUERIES
    # ========================================================

    def is_connected(
        self,
        node_id: str,
    ) -> bool:

        with self._connections_lock:
            return node_id in self._connections

    def connected_node_ids(self) -> list[str]:

        with self._connections_lock:
            return list(
                self._connections.keys()
            )

    # ========================================================
    # STOP
    # ========================================================

    def stop(self) -> None:
        """
        Stop listener and close active connections.
        """

        if not self._running:
            return

        self._running = False

        server = self._server_socket
        self._server_socket = None

        if server is not None:

            try:
                server.close()
            except OSError:
                pass

        with self._connections_lock:

            connections = list(
                self._connections.values()
            )

            self._connections.clear()

        for connection in connections:

            try:
                connection.close()
            except OSError:
                pass

            self.node.mark_peer_disconnected(
                connection.identity.node_id
            )

        accept_thread = self._accept_thread

        if (
            accept_thread is not None
            and accept_thread.is_alive()
            and accept_thread
            is not threading.current_thread()
        ):
            accept_thread.join(
                timeout=2.0
            )

        self._accept_thread = None

    # ========================================================
    # STATUS
    # ========================================================

    @property
    def running(self) -> bool:
        return self._running

    def stats(self) -> dict[str, int | bool | str]:
        with self._connections_lock:
            active = len(
                self._connections
            )

        return {
            "running": self._running,
            "host": self.host,
            "port": self.port,
            "active_connections": active,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "connection_attempts": self.connection_attempts,
            "connection_failures": self.connection_failures,
        }


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 70)
    print("NEXCHAIN TCP P2P TRANSPORT TEST")
    print("=" * 70)

    # --------------------------------------------------------
    # Nodes
    # --------------------------------------------------------

    node_a = NetworkNode(
        address=DEFAULT_HOST,
        port=41011,
    )

    node_b = NetworkNode(
        address=DEFAULT_HOST,
        port=41012,
    )

    transport_a = TCPTransport(
        node=node_a,
        host=DEFAULT_HOST,
        port=41011,
    )

    transport_b = TCPTransport(
        node=node_b,
        host=DEFAULT_HOST,
        port=41012,
    )

    try:

        # ----------------------------------------------------
        # Frame codec
        # ----------------------------------------------------

        message = node_a.create_ping()

        frame = FrameCodec.encode(
            message
        )

        decoded = FrameCodec.decode_frame(
            frame
        )

        assert (
            decoded.message_id
            == message.message_id
        )

        print("[PASS] TCP frame encoding/decoding")

        # ----------------------------------------------------
        # Start node A
        # ----------------------------------------------------

        transport_a.start()

        assert transport_a.running

        print("[PASS] TCP server A started")

        # ----------------------------------------------------
        # Start node B
        # ----------------------------------------------------

        transport_b.start()

        assert transport_b.running

        print("[PASS] TCP server B started")

        # ----------------------------------------------------
        # Connect B -> A
        # ----------------------------------------------------

        connected, reason = transport_b.connect(
            DEFAULT_HOST,
            41011,
        )

        assert connected, reason

        print("[PASS] TCP peer connection")

        # ----------------------------------------------------
        # Wait for connection state
        # ----------------------------------------------------

        deadline = time.time() + 3.0

        while time.time() < deadline:

            if (
                transport_a.is_connected(
                    node_b.identity.node_id
                )
                and transport_b.is_connected(
                    node_a.identity.node_id
                )
            ):
                break

            time.sleep(0.05)

        assert transport_a.is_connected(
            node_b.identity.node_id
        )

        assert transport_b.is_connected(
            node_a.identity.node_id
        )

        print("[PASS] Bidirectional connection state")

        # ----------------------------------------------------
        # Ping
        # ----------------------------------------------------

        ping = node_b.create_ping()

        sent, reason = transport_b.send(
            node_a.identity.node_id,
            ping,
        )

        assert sent, reason

        print("[PASS] Ping transmitted")

        # ----------------------------------------------------
        # Wait for pong
        # ----------------------------------------------------

        deadline = time.time() + 3.0

        while time.time() < deadline:

            if (
                transport_a.messages_received
                > 0
            ):
                break

            time.sleep(0.05)

        assert (
            transport_a.messages_received
            > 0
        )

        print("[PASS] Message received")

        # ----------------------------------------------------
        # Peer discovery
        # ----------------------------------------------------

        get_peers = node_b.create_get_peers()

        sent, reason = transport_b.send(
            node_a.identity.node_id,
            get_peers,
        )

        assert sent, reason

        print("[PASS] Peer discovery request")

        # ----------------------------------------------------
        # Broadcast
        # ----------------------------------------------------

        broadcast_message = (
            node_b.create_ping()
        )

        count = transport_b.broadcast(
            broadcast_message
        )

        assert count >= 1

        print("[PASS] Broadcast transmission")

        # ----------------------------------------------------
        # Connection stats
        # ----------------------------------------------------

        stats_a = transport_a.stats()
        stats_b = transport_b.stats()

        assert (
            stats_a["active_connections"]
            >= 1
        )

        assert (
            stats_b["active_connections"]
            >= 1
        )

        print("[PASS] Transport statistics")

        # ----------------------------------------------------
        # Graceful shutdown
        # ----------------------------------------------------

    finally:

        transport_a.stop()
        transport_b.stop()

    assert not transport_a.running
    assert not transport_b.running

    print("[PASS] Graceful shutdown")

    print()
    print("Transport A statistics:")
    print(stats_a)

    print()
    print("Transport B statistics:")
    print(stats_b)

    print()
    print("=" * 70)
    print("ALL TCP P2P TRANSPORT TESTS PASSED")
    print("=" * 70)


if __name__ == "__main__":
    self_test()