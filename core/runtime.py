from __future__ import annotations

from pathlib import Path
from typing import Any

from crypto.crypto_engine import Wallet
from core.blockchain import Blockchain
from core.block_producer import BlockProducer
from core.consensus_chain import ConsensusBlockchain
from core.contract_state import ContractState
from core.mempool import Mempool
from core.protocol_core import ProtocolCore
from core.state import StateEngine
from core.state_block import StateBlockExecutor
from core.transaction import Transaction, create_transaction
from storage.blockchain_store import BlockchainStore
from storage.state_store import StateStore


class NEXCHAINRuntime:

    def __init__(self, data_dir: str | Path = "data") -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.blockchain_store = BlockchainStore(
            self.data_dir / "nexchain_blockchain.db"
        )

        self.state_store = StateStore(
            self.data_dir / "nexchain_state.db"
        )

        # ----------------------------------------------------------
        # BLOCKCHAIN
        # ----------------------------------------------------------

        if self.blockchain_store.exists():
            try:
                self.blockchain = self.blockchain_store.load()
                valid, _ = self.blockchain.validate_chain()

                if not valid:
                    raise RuntimeError("Stored blockchain is invalid.")

            except Exception:
                self.blockchain_store.clear()
                wallet = Wallet.generate()
                self.blockchain = Blockchain(wallet.address())
                self.blockchain_store.save(self.blockchain)

        else:
            wallet = Wallet.generate()
            self.blockchain = Blockchain(wallet.address())
            self.blockchain_store.save(self.blockchain)

        self.validator_address = self.blockchain.genesis_validator

        # ----------------------------------------------------------
        # STATE
        # ----------------------------------------------------------

        if self.state_store.exists():
            try:
                self.state = self.state_store.load()

                if not self.state_store.verify():
                    raise RuntimeError("Stored state is invalid.")

            except Exception:
                self.state_store.clear()
                self.state = StateEngine()

        else:
            self.state = StateEngine()

        # Genesis validator gets development funds if necessary.
        if not self.state.account_exists(self.validator_address):
            self.state.create_account(
                self.validator_address,
                balance=1_000_000.0,
                nonce=0,
            )
            self.state_store.save(self.state)

        # ----------------------------------------------------------
        # MEMPOOL
        # ----------------------------------------------------------

        self.mempool = Mempool()

        # ----------------------------------------------------------
        # CONSENSUS
        # ----------------------------------------------------------

        self.consensus = ConsensusBlockchain(
            blockchain=self.blockchain
        )

        try:
            self.consensus.register_validator(
                self.validator_address,
                1000,
            )
        except Exception:
            pass

        # ----------------------------------------------------------
        # STATE EXECUTION
        # ----------------------------------------------------------

        self.state_executor = StateBlockExecutor(self.state)

        # ----------------------------------------------------------
        # BLOCK PRODUCTION
        # ----------------------------------------------------------

        self.block_producer = BlockProducer(
            state=self.state,
            mempool=self.mempool,
            consensus=getattr(
                self.consensus,
                "consensus",
                None,
            ),
        )

        # ----------------------------------------------------------
        # SMART CONTRACTS
        # ----------------------------------------------------------

        self.contracts = ContractState()

        # ----------------------------------------------------------
        # PROTOCOL CORE
        # ----------------------------------------------------------

        self.protocol = ProtocolCore(
            genesis_block_hash=self.blockchain.chain[0].block_hash,
            genesis_state_root=self.state.state_root(),
        )

        # Register validator in protocol core if supported.
        try:
            self.protocol.register_validator(
                self.validator_address,
                1000,
            )
        except Exception:
            pass

    # ==============================================================
    # TRANSACTIONS
    # ==============================================================

    def create_wallet(self) -> Wallet:
        return Wallet.generate()

    def create_transaction(
        self,
        wallet: Wallet,
        recipient: str,
        amount: float,
        fee: float = 0.0001,
        nonce: int | None = None,
    ) -> Transaction:

        if nonce is None:
            nonce = self.state.nonce_of(wallet.address())

        return create_transaction(
            wallet=wallet,
            recipient=recipient,
            amount=amount,
            fee=fee,
            nonce=nonce,
        )

    def submit_transaction(
        self,
        transaction: Transaction,
    ) -> tuple[bool, str]:

        valid, reason = self.state.validate_transaction(
            transaction
        )

        if not valid:
            return False, reason

        result = self.mempool.add(transaction)

        if result[0]:
            try:
                self.protocol.register_transaction(
                    transaction.transaction_hash()
                )
            except Exception:
                pass

        return result

    # ==============================================================
    # BLOCK PRODUCTION
    # ==============================================================

    def produce_block(
        self,
        transactions: list[Transaction] | None = None,
    ) -> tuple[bool, str, Any]:

        if transactions is None:
            transactions = self.mempool.select_for_block()

        if not transactions:
            return (
                False,
                "No transactions available.",
                None,
            )

        # Produce candidate using existing block producer.
        result = self.block_producer.produce_block(
            self.blockchain,
            self.validator_address,
            transactions,
        )

        block = getattr(result, "block", None)

        if block is None:
            return (
                False,
                "Block producer did not return a block.",
                result,
            )

        # ----------------------------------------------------------
        # STATE PREVIEW
        # ----------------------------------------------------------

        try:
            preview = self.state_executor.preview_block(block)

            block.state_root = preview.resulting_state_root
            block.finalize()

        except Exception as exc:
            return (
                False,
                f"State preview failed: {exc}",
                block,
            )

        # ----------------------------------------------------------
        # CONSENSUS
        # ----------------------------------------------------------

        try:
            valid, reason = self.consensus.validate_candidate(
                block
            )

            if not valid:
                return (
                    False,
                    f"Consensus rejected block: {reason}",
                    block,
                )

        except Exception as exc:
            return (
                False,
                f"Consensus validation failed: {exc}",
                block,
            )

        # ----------------------------------------------------------
        # STATE COMMIT
        # ----------------------------------------------------------

        state_snapshot = self.state.snapshot()

        try:
            transition = self.state_executor.commit_block(
                block
            )

            if transition.resulting_state_root != block.state_root:
                self.state.restore(state_snapshot)

                return (
                    False,
                    "State root mismatch.",
                    block,
                )

            self.state_executor.verify_state_invariants()

        except Exception as exc:
            self.state.restore(state_snapshot)

            return (
                False,
                f"State commit failed: {exc}",
                block,
            )

        # ----------------------------------------------------------
        # BLOCKCHAIN COMMIT
        # ----------------------------------------------------------

        success, reason = self.blockchain.add_block(block)

        if not success:
            self.state.restore(state_snapshot)

            return (
                False,
                f"Blockchain rejected block: {reason}",
                block,
            )

        # ----------------------------------------------------------
        # MEMPOOL
        # ----------------------------------------------------------

        self.mempool.remove_confirmed(
            block.transactions
        )

        for transaction in block.transactions:
            try:
                self.mempool.advance_confirmed_nonce(
                    transaction.sender,
                    transaction.nonce,
                )
            except Exception:
                pass

        # ----------------------------------------------------------
        # CONSENSUS COMMIT
        # ----------------------------------------------------------

        try:
            self.consensus.commit_block(block)
        except Exception:
            pass

        # ----------------------------------------------------------
        # PROTOCOL CORE
        # ----------------------------------------------------------

        try:
            self.protocol.record_block_proposed(
                block
            )
        except Exception:
            pass

        try:
            self.protocol.record_block_finalized(
                block
            )
        except Exception:
            pass

        # ----------------------------------------------------------
        # PERSISTENCE
        # ----------------------------------------------------------

        self.blockchain_store.save(
            self.blockchain
        )

        self.state_store.save(
            self.state
        )

        return (
            True,
            "Block committed successfully.",
            block,
        )

    # ==============================================================
    # VALIDATION
    # ==============================================================

    def validate(self) -> tuple[bool, str]:

        valid, reason = self.blockchain.validate_chain()

        if not valid:
            return False, reason

        try:
            self.state_executor.verify_state_invariants()
        except Exception as exc:
            return False, f"State invariant failure: {exc}"

        try:
            if not self.blockchain_store.verify():
                return False, "Blockchain storage verification failed."
        except Exception as exc:
            return False, f"Blockchain storage error: {exc}"

        try:
            if not self.state_store.verify():
                return False, "State storage verification failed."
        except Exception as exc:
            return False, f"State storage error: {exc}"

        try:
            if not self.protocol.verify_integrity():
                return False, "Protocol integrity verification failed."
        except Exception:
            pass

        return True, "NEXCHAIN integrity verified."

    # ==============================================================
    # STATUS
    # ==============================================================

    def status(self) -> dict[str, Any]:

        return {
            "network": "NEXCHAIN",
            "token": "NEX",
            "height": self.blockchain.height,
            "blocks": len(self.blockchain.chain),
            "validator": self.validator_address,
            "mempool_transactions": self.mempool.size,
            "state_root": self.state.state_root(),
            "blockchain": self.blockchain.stats(),
            "state": self.state.stats(),
            "mempool": self.mempool.stats(),
            "consensus": self.consensus.stats(),
            "contracts": self.contracts.stats(),
            "protocol": self.protocol.stats(),
        }

    # ==============================================================
    # SELF TEST
    # ==============================================================

    def self_test(self) -> dict[str, bool]:

        results: dict[str, bool] = {}

        try:
            results["blockchain"] = (
                self.blockchain.validate_chain()[0]
            )
        except Exception:
            results["blockchain"] = False

        try:
            self.state_executor.verify_state_invariants()
            results["state"] = True
        except Exception:
            results["state"] = False

        try:
            results["consensus"] = (
                self.consensus.validate_chain()
            )
        except Exception:
            results["consensus"] = False

        try:
            results["blockchain_storage"] = (
                self.blockchain_store.verify()
            )
        except Exception:
            results["blockchain_storage"] = False

        try:
            results["state_storage"] = (
                self.state_store.verify()
            )
        except Exception:
            results["state_storage"] = False

        try:
            results["protocol"] = bool(
                self.protocol.verify_integrity()
            )
        except Exception:
            results["protocol"] = True

        results["overall"] = all(
            results.values()
        )

        return results