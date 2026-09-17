from __future__ import annotations

import threading
from typing import Any

from api.keystore import WalletStore
from core.contract_vm import ContractProgram
from core.runtime import NEXCHAINRuntime
from core.transaction import Transaction


class NEXCHAINService:

    def __init__(
        self,
        data_dir: str = "data",
    ) -> None:
        self.runtime = NEXCHAINRuntime(
            data_dir=data_dir
        )

        self.wallets = WalletStore(
            f"{data_dir}/wallets"
        )

        self.lock = threading.RLock()

    # ============================================================
    # NETWORK
    # ============================================================

    def health(self) -> dict[str, Any]:
        with self.lock:
            valid, reason = (
                self.runtime.validate()
            )

            return {
                "ok": bool(valid),
                "network": "NEXCHAIN",
                "token": "NEX",
                "height": self.runtime.blockchain.height,
                "state_root": (
                    self.runtime.state.state_root()
                ),
                "reason": reason,
            }

    def status(self) -> dict[str, Any]:
        with self.lock:
            return {
                "network": "NEXCHAIN",
                "token": "NEX",
                "protocol_version": 1,
                "height": self.runtime.blockchain.height,
                "blocks": len(
                    self.runtime.blockchain.chain
                ),
                "validator": (
                    self.runtime.validator_address
                ),
                "mempool_transactions": (
                    self.runtime.mempool.size
                ),
                "state_root": (
                    self.runtime.state.state_root()
                ),
                "blockchain": (
                    self.runtime.blockchain.stats()
                ),
                "state": (
                    self.runtime.state.stats()
                ),
                "mempool": (
                    self.runtime.mempool.stats()
                ),
                "consensus": (
                    self.runtime.consensus.stats()
                ),
                "contracts": (
                    self.runtime.contracts.stats()
                ),
                "protocol": (
                    self.runtime.protocol.stats()
                ),
            }

    def validate(self) -> dict[str, Any]:
        with self.lock:
            valid, reason = (
                self.runtime.validate()
            )

            return {
                "valid": bool(valid),
                "reason": reason,
            }

    # ============================================================
    # BLOCKCHAIN
    # ============================================================

    def list_blocks(
        self,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        limit = max(
            1,
            min(int(limit), 100),
        )

        with self.lock:
            blocks = (
                self.runtime.blockchain.chain[-limit:]
            )

            return [
                block.to_dict()
                for block in reversed(blocks)
            ]

    def get_block(
        self,
        height: int,
    ) -> dict[str, Any]:
        with self.lock:
            height = int(height)

            if (
                height < 0
                or height
                >= len(
                    self.runtime.blockchain.chain
                )
            ):
                raise KeyError(
                    "Block not found."
                )

            return (
                self.runtime.blockchain
                .chain[height]
                .to_dict()
            )

    def get_transaction(
        self,
        transaction_hash: str,
    ) -> dict[str, Any]:
        with self.lock:
            found = (
                self.runtime.blockchain
                .find_transaction(
                    transaction_hash
                )
            )

            if found is not None:
                height, transaction = found

                return {
                    "status": "confirmed",
                    "block_height": height,
                    "transaction": (
                        transaction.to_dict()
                    ),
                    "transaction_hash": (
                        transaction.transaction_hash()
                    ),
                }

            pending = (
                self.runtime.mempool.get(
                    transaction_hash
                )
            )

            if pending is not None:
                return {
                    "status": "pending",
                    "block_height": None,
                    "transaction": (
                        pending.to_dict()
                    ),
                    "transaction_hash": (
                        pending.transaction_hash()
                    ),
                }

            raise KeyError(
                "Transaction not found."
            )

    # ============================================================
    # ADDRESS / ACCOUNT
    # ============================================================

    def get_address(
        self,
        address: str,
    ) -> dict[str, Any]:

        if (
            not isinstance(address, str)
            or not address.startswith("NEX")
            or len(address) != 43
        ):
            raise ValueError(
                "Invalid NEXCHAIN address."
            )

        with self.lock:
            account = (
                self.runtime.state.accounts.get(
                    address
                )
            )

            history = []

            for block in (
                self.runtime.blockchain.chain
            ):
                for transaction in (
                    block.transactions
                ):
                    if (
                        transaction.sender
                        == address
                        or transaction.recipient
                        == address
                    ):
                        history.append(
                            {
                                "block_height": (
                                    block.height
                                ),
                                "transaction": (
                                    transaction.to_dict()
                                ),
                                "transaction_hash": (
                                    transaction.transaction_hash()
                                ),
                            }
                        )

            return {
                "address": address,
                "exists": account is not None,
                "balance": (
                    self.runtime.state
                    .balance_of(address)
                ),
                "nonce": (
                    self.runtime.state
                    .nonce_of(address)
                ),
                "pending_transactions": [
                    tx.to_dict()
                    for tx in (
                        self.runtime.mempool
                        .get_sender_transactions(
                            address
                        )
                    )
                ],
                "transactions": history[-100:],
            }

    # ============================================================
    # MEMPOOL
    # ============================================================

    def mempool(self) -> dict[str, Any]:
        with self.lock:
            return self.runtime.mempool.stats()

    # ============================================================
    # CONSENSUS
    # ============================================================

    def validators(self) -> list[dict[str, Any]]:
        with self.lock:
            return [
                validator.to_dict()
                for validator in (
                    self.runtime
                    .consensus
                    .consensus
                    .validators
                    .values()
                )
            ]

    # ============================================================
    # TRANSACTIONS
    # ============================================================

    def submit_raw_transaction(
        self,
        payload: dict[str, Any],
    ) -> dict[str, Any]:

        transaction = (
            Transaction.from_dict(payload)
        )

        with self.lock:
            accepted, reason = (
                self.runtime
                .submit_transaction(
                    transaction
                )
            )

            if not accepted:
                raise ValueError(reason)

            return {
                "accepted": True,
                "reason": reason,
                "transaction_hash": (
                    transaction.transaction_hash()
                ),
                "transaction": (
                    transaction.to_dict()
                ),
            }

    # ============================================================
    # WALLETS
    # ============================================================

    def create_wallet(
        self,
        password: str,
    ) -> dict[str, Any]:
        with self.lock:
            return self.wallets.create(
                password
            )

    def import_wallet(
        self,
        private_key: str,
        password: str,
    ) -> dict[str, Any]:
        with self.lock:
            return (
                self.wallets.import_private_key(
                    private_key,
                    password,
                )
            )

    def list_wallets(self) -> list[dict]:
        with self.lock:
            return self.wallets.list_wallets()

    def export_wallet(
        self,
        address: str,
        password: str,
    ) -> dict[str, Any]:
        with self.lock:
            return {
                "address": address,
                "private_key": (
                    self.wallets
                    .export_private_key(
                        address,
                        password,
                    )
                ),
            }

    def send_from_wallet(
        self,
        address: str,
        password: str,
        recipient: str,
        amount: float,
        fee: float = 0.0001,
        nonce: int | None = None,
    ) -> dict[str, Any]:

        with self.lock:
            wallet = (
                self.wallets.unlock(
                    address,
                    password,
                )
            )

            if nonce is None:
                nonce = (
                    self.runtime.state
                    .nonce_of(address)
                )

            transaction = (
                self.runtime.create_transaction(
                    wallet=wallet,
                    recipient=recipient,
                    amount=float(amount),
                    fee=float(fee),
                    nonce=int(nonce),
                )
            )

            accepted, reason = (
                self.runtime
                .submit_transaction(
                    transaction
                )
            )

            if not accepted:
                raise ValueError(reason)

            return {
                "accepted": True,
                "reason": reason,
                "transaction_hash": (
                    transaction.transaction_hash()
                ),
                "transaction": (
                    transaction.to_dict()
                ),
            }

    # ============================================================
    # CONTRACTS
    # ============================================================

    def contracts(self) -> dict[str, Any]:
        with self.lock:
            return (
                self.runtime.contracts.to_dict()
            )

    def get_contract(
        self,
        address: str,
    ) -> dict[str, Any]:
        with self.lock:
            return (
                self.runtime.contracts
                .get_contract(address)
                .to_dict()
            )

    def deploy_contract(
        self,
        deployer: str,
        program_data: dict[str, Any],
        initial_storage: dict[str, Any]
        | None = None,
    ) -> dict[str, Any]:

        with self.lock:
            program = (
                ContractProgram.from_dict(
                    program_data
                )
            )

            storage = {
                int(key): int(value)
                for key, value in (
                    initial_storage or {}
                ).items()
            }

            contract = (
                self.runtime.contracts.deploy(
                    deployer,
                    program,
                    initial_storage=storage,
                )
            )

            return contract.to_dict()

    def read_contract_storage(
        self,
        address: str,
        key: int,
    ) -> dict[str, Any]:

        with self.lock:
            return {
                "address": address,
                "key": int(key),
                "value": (
                    self.runtime
                    .contracts
                    .read_storage(
                        address,
                        int(key),
                    )
                ),
            }

    def call_contract(
        self,
        address: str,
        gas_limit: int = 100_000,
        initial_stack: list[int]
        | None = None,
    ) -> dict[str, Any]:

        with self.lock:
            receipt = (
                self.runtime.contracts.call(
                    address,
                    gas_limit=int(
                        gas_limit
                    ),
                    initial_stack=(
                        initial_stack
                    ),
                )
            )

            return receipt.to_dict()

    # ============================================================
    # BLOCK PRODUCTION
    # ============================================================

    def produce_block(self) -> dict[str, Any]:

        with self.lock:
            success, reason, block = (
                self.runtime.produce_block()
            )

            if not success:
                raise ValueError(reason)

            return {
                "success": True,
                "reason": reason,
                "block": block.to_dict(),
            }

    # ============================================================
    # TESTING
    # ============================================================

    def self_test(self) -> dict[str, bool]:
        with self.lock:
            return self.runtime.self_test()