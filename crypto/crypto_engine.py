"""
NEXCHAIN Cryptographic Engine
============================

Core cryptographic primitives for the NEXCHAIN blockchain.

Features:
- SHA-256 hashing
- Secure Ed25519 key generation
- Public/private key serialization
- NEXCHAIN address generation
- Digital signatures
- Signature verification
- Deterministic message hashing
"""

from __future__ import annotations

import base64
import hashlib
import json
from dataclasses import dataclass

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)


# ============================================================
# HASHING
# ============================================================

def sha256(data: bytes) -> str:
    """
    Return the SHA-256 hexadecimal digest of raw bytes.
    """
    return hashlib.sha256(data).hexdigest()


def hash_text(text: str) -> str:
    """
    SHA-256 hash of UTF-8 text.
    """
    return sha256(text.encode("utf-8"))


def double_sha256(data: bytes) -> str:
    """
    Bitcoin-style double SHA-256.
    """
    first = hashlib.sha256(data).digest()
    second = hashlib.sha256(first).hexdigest()
    return second


# ============================================================
# DETERMINISTIC SERIALIZATION
# ============================================================

def canonical_json(data: dict) -> bytes:
    """
    Convert a dictionary into deterministic JSON bytes.

    Sorting keys and removing unnecessary whitespace ensures
    every NEXCHAIN node hashes the exact same representation.
    """
    return json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def hash_object(data: dict) -> str:
    """
    Deterministically hash a dictionary.
    """
    return sha256(canonical_json(data))


# ============================================================
# BASE64 HELPERS
# ============================================================

def encode_bytes(data: bytes) -> str:
    """
    Encode bytes using URL-safe Base64 without padding.
    """
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def decode_bytes(data: str) -> bytes:
    """
    Decode URL-safe Base64 without padding.
    """
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


# ============================================================
# WALLET
# ============================================================

@dataclass
class Wallet:
    """
    NEXCHAIN wallet.

    Uses Ed25519 for fast and secure digital signatures.
    """

    private_key: Ed25519PrivateKey
    public_key: Ed25519PublicKey

    @classmethod
    def generate(cls) -> "Wallet":
        """
        Generate a cryptographically secure new wallet.
        """
        private_key = Ed25519PrivateKey.generate()
        public_key = private_key.public_key()

        return cls(
            private_key=private_key,
            public_key=public_key,
        )

    # --------------------------------------------------------
    # KEY SERIALIZATION
    # --------------------------------------------------------

    def private_key_bytes(self) -> bytes:
        """
        Return raw 32-byte private key.
        """
        return self.private_key.private_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PrivateFormat.Raw,
            encryption_algorithm=serialization.NoEncryption(),
        )

    def public_key_bytes(self) -> bytes:
        """
        Return raw 32-byte public key.
        """
        return self.public_key.public_bytes(
            encoding=serialization.Encoding.Raw,
            format=serialization.PublicFormat.Raw,
        )

    def private_key_encoded(self) -> str:
        """
        Return Base64 encoded private key.
        """
        return encode_bytes(self.private_key_bytes())

    def public_key_encoded(self) -> str:
        """
        Return Base64 encoded public key.
        """
        return encode_bytes(self.public_key_bytes())

    # --------------------------------------------------------
    # ADDRESS
    # --------------------------------------------------------

    def address(self) -> str:
        """
        Generate a deterministic NEXCHAIN address.

        Format:
            NEX + first 40 hexadecimal characters of SHA-256
            of the public key.
        """
        public_key_hash = sha256(self.public_key_bytes())

        return "NEX" + public_key_hash[:40]

    # --------------------------------------------------------
    # SIGNING
    # --------------------------------------------------------

    def sign(self, message: bytes) -> str:
        """
        Sign raw message bytes using Ed25519.
        """
        signature = self.private_key.sign(message)
        return encode_bytes(signature)

    def sign_text(self, text: str) -> str:
        """
        Sign UTF-8 text.
        """
        return self.sign(text.encode("utf-8"))

    def sign_object(self, data: dict) -> str:
        """
        Sign a deterministic dictionary representation.
        """
        return self.sign(canonical_json(data))


# ============================================================
# PUBLIC VERIFICATION
# ============================================================

def public_key_from_encoded(encoded_key: str) -> Ed25519PublicKey:
    """
    Reconstruct an Ed25519 public key from encoded bytes.
    """
    raw_key = decode_bytes(encoded_key)

    if len(raw_key) != 32:
        raise ValueError("Invalid Ed25519 public key length.")

    return Ed25519PublicKey.from_public_bytes(raw_key)


def verify_signature(
    public_key_encoded: str,
    message: bytes,
    signature_encoded: str,
) -> bool:
    """
    Verify an Ed25519 signature.

    Returns:
        True  -> valid signature
        False -> invalid signature
    """
    try:
        public_key = public_key_from_encoded(public_key_encoded)
        signature = decode_bytes(signature_encoded)

        public_key.verify(signature, message)

        return True

    except (InvalidSignature, ValueError):
        return False


def verify_text_signature(
    public_key_encoded: str,
    text: str,
    signature_encoded: str,
) -> bool:
    """
    Verify a signature against UTF-8 text.
    """
    return verify_signature(
        public_key_encoded,
        text.encode("utf-8"),
        signature_encoded,
    )


def verify_object_signature(
    public_key_encoded: str,
    data: dict,
    signature_encoded: str,
) -> bool:
    """
    Verify a signature against a deterministic dictionary.
    """
    return verify_signature(
        public_key_encoded,
        canonical_json(data),
        signature_encoded,
    )


# ============================================================
# WALLET IMPORT
# ============================================================

def wallet_from_private_key(encoded_private_key: str) -> Wallet:
    """
    Reconstruct a wallet from an encoded raw private key.
    """
    raw_private_key = decode_bytes(encoded_private_key)

    if len(raw_private_key) != 32:
        raise ValueError("Invalid Ed25519 private key length.")

    private_key = Ed25519PrivateKey.from_private_bytes(
        raw_private_key
    )

    return Wallet(
        private_key=private_key,
        public_key=private_key.public_key(),
    )


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:
    """
    Run internal cryptographic integrity tests.
    """

    print("=" * 60)
    print("NEXCHAIN CRYPTOGRAPHIC ENGINE TEST")
    print("=" * 60)

    # Hash test
    text = "NEXCHAIN"

    digest = hash_text(text)

    assert len(digest) == 64
    print("[PASS] SHA-256")

    # Wallet generation
    wallet = Wallet.generate()

    assert len(wallet.private_key_bytes()) == 32
    assert len(wallet.public_key_bytes()) == 32

    print("[PASS] Ed25519 key generation")

    # Address
    address = wallet.address()

    assert address.startswith("NEX")
    assert len(address) == 43

    print("[PASS] NEXCHAIN address generation")
    print(f"       Address: {address}")

    # Signature
    message = b"NEXCHAIN TEST TRANSACTION"

    signature = wallet.sign(message)

    assert verify_signature(
        wallet.public_key_encoded(),
        message,
        signature,
    )

    print("[PASS] Digital signature")

    # Tamper test
    tampered = b"NEXCHAIN TAMPERED TRANSACTION"

    assert not verify_signature(
        wallet.public_key_encoded(),
        tampered,
        signature,
    )

    print("[PASS] Tamper detection")

    # Deterministic object test
    obj = {
        "amount": 100,
        "recipient": "NEX123",
        "sender": address,
    }

    object_signature = wallet.sign_object(obj)

    assert verify_object_signature(
        wallet.public_key_encoded(),
        obj,
        object_signature,
    )

    print("[PASS] Deterministic object signing")

    # Wallet recovery test
    exported_private = wallet.private_key_encoded()

    restored = wallet_from_private_key(exported_private)

    assert restored.address() == wallet.address()

    print("[PASS] Wallet recovery")

    print("=" * 60)
    print("ALL CRYPTOGRAPHIC TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    self_test()