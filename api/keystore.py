from __future__ import annotations

import base64
import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from crypto.crypto_engine import Wallet, wallet_from_private_key


class WalletStore:
    VERSION = 1
    KDF_ITERATIONS = 600_000
    SALT_BYTES = 16
    NONCE_BYTES = 12

    def __init__(self, directory: str | Path = "data/wallets") -> None:
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _encode(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).decode("ascii")

    @staticmethod
    def _decode(value: str) -> bytes:
        return base64.urlsafe_b64decode(value.encode("ascii"))

    @classmethod
    def _derive_key(cls, password: str, salt: bytes) -> bytes:
        if not isinstance(password, str) or len(password) < 8:
            raise ValueError(
                "Wallet password must contain at least 8 characters."
            )

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=cls.KDF_ITERATIONS,
        )

        return kdf.derive(password.encode("utf-8"))

    @staticmethod
    def _validate_address(address: str) -> None:
        if (
            not isinstance(address, str)
            or not address.startswith("NEX")
            or len(address) != 43
        ):
            raise ValueError("Invalid NEXCHAIN wallet address.")

    def _path(self, address: str) -> Path:
        self._validate_address(address)
        return self.directory / f"{address}.json"

    def _save_wallet(
        self,
        wallet: Wallet,
        password: str,
    ) -> dict:
        address = wallet.address()
        path = self._path(address)

        if path.exists():
            raise FileExistsError("Wallet already exists.")

        salt = secrets.token_bytes(self.SALT_BYTES)
        nonce = secrets.token_bytes(self.NONCE_BYTES)

        key = self._derive_key(password, salt)

        ciphertext = AESGCM(key).encrypt(
            nonce,
            wallet.private_key_bytes(),
            address.encode("utf-8"),
        )

        record = {
            "version": self.VERSION,
            "address": address,
            "public_key": wallet.public_key_encoded(),
            "kdf": "PBKDF2-HMAC-SHA256",
            "iterations": self.KDF_ITERATIONS,
            "cipher": "AES-256-GCM",
            "salt": self._encode(salt),
            "nonce": self._encode(nonce),
            "ciphertext": self._encode(ciphertext),
        }

        temporary = path.with_suffix(".tmp")

        temporary.write_text(
            json.dumps(
                record,
                sort_keys=True,
                indent=2,
            ),
            encoding="utf-8",
        )

        os.replace(temporary, path)

        return {
            "address": address,
            "public_key": wallet.public_key_encoded(),
            "keystore": str(path),
        }

    def create(self, password: str) -> dict:
        return self._save_wallet(
            Wallet.generate(),
            password,
        )

    def import_private_key(
        self,
        private_key: str,
        password: str,
    ) -> dict:
        wallet = wallet_from_private_key(private_key)

        return self._save_wallet(
            wallet,
            password,
        )

    def list_wallets(self) -> list[dict]:
        wallets = []

        for path in sorted(
            self.directory.glob("NEX*.json")
        ):
            try:
                record = json.loads(
                    path.read_text(
                        encoding="utf-8"
                    )
                )

                wallets.append(
                    {
                        "address": record["address"],
                        "public_key": record.get(
                            "public_key",
                            "",
                        ),
                        "keystore": str(path),
                        "version": record.get(
                            "version"
                        ),
                    }
                )

            except (
                OSError,
                ValueError,
                KeyError,
                json.JSONDecodeError,
            ):
                continue

        return wallets

    def unlock(
        self,
        address: str,
        password: str,
    ) -> Wallet:
        path = self._path(address)

        if not path.exists():
            raise FileNotFoundError(
                "Wallet not found."
            )

        record = json.loads(
            path.read_text(
                encoding="utf-8"
            )
        )

        if int(
            record.get("version", 0)
        ) != self.VERSION:
            raise ValueError(
                "Unsupported wallet keystore version."
            )

        if record.get("address") != address:
            raise ValueError(
                "Wallet address/keystore mismatch."
            )

        salt = self._decode(
            record["salt"]
        )

        nonce = self._decode(
            record["nonce"]
        )

        ciphertext = self._decode(
            record["ciphertext"]
        )

        key = self._derive_key(
            password,
            salt,
        )

        try:
            private_key = AESGCM(key).decrypt(
                nonce,
                ciphertext,
                address.encode("utf-8"),
            )
        except Exception as exc:
            raise ValueError(
                "Invalid wallet password or corrupted keystore."
            ) from exc

        if len(private_key) != 32:
            raise ValueError(
                "Invalid decrypted private key."
            )

        private = (
            Ed25519PrivateKey.from_private_bytes(
                private_key
            )
        )

        wallet = Wallet(
            private_key=private,
            public_key=private.public_key(),
        )

        if wallet.address() != address:
            raise ValueError(
                "Recovered wallet address mismatch."
            )

        return wallet

    def export_private_key(
        self,
        address: str,
        password: str,
    ) -> str:
        wallet = self.unlock(
            address,
            password,
        )

        return wallet.private_key_encoded()