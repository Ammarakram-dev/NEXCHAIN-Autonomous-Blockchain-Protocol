"""
NEXCHAIN Merkle Tree Engine
===========================

A deterministic binary Merkle tree implementation.

Used by NEXCHAIN blocks to commit cryptographically
to all transactions contained within a block.
"""

from __future__ import annotations

from crypto.crypto_engine import double_sha256


class MerkleTree:
    """
    Binary Merkle tree.

    Leaves:
        Transaction hashes

    Root:
        Single cryptographic commitment representing
        the complete transaction set.
    """

    def __init__(self, leaves: list[str]):
        if not leaves:
            raise ValueError("Merkle tree requires at least one leaf.")

        self.leaves = list(leaves)
        self.root = self._build_root(self.leaves)

    # ========================================================
    # HASH PAIR
    # ========================================================

    @staticmethod
    def hash_pair(left: str, right: str) -> str:
        """
        Hash two hexadecimal hashes together.

        Double SHA-256 is used for the Merkle construction.
        """

        combined = bytes.fromhex(left) + bytes.fromhex(right)

        return double_sha256(combined)

    # ========================================================
    # BUILD
    # ========================================================

    @classmethod
    def _build_root(cls, leaves: list[str]) -> str:
        """
        Build the tree until only one hash remains.
        """

        current_level = list(leaves)

        while len(current_level) > 1:

            # Duplicate final node when the level has
            # an odd number of elements.
            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            next_level = []

            for index in range(0, len(current_level), 2):
                left = current_level[index]
                right = current_level[index + 1]

                parent = cls.hash_pair(left, right)

                next_level.append(parent)

            current_level = next_level

        return current_level[0]

    # ========================================================
    # ROOT
    # ========================================================

    def get_root(self) -> str:
        """
        Return the Merkle root.
        """

        return self.root

    # ========================================================
    # PROOF
    # ========================================================

    def generate_proof(self, leaf_index: int) -> list[dict]:
        """
        Generate a Merkle inclusion proof for a leaf.

        The proof contains sibling hashes and their positions.
        """

        if leaf_index < 0 or leaf_index >= len(self.leaves):
            raise IndexError("Invalid leaf index.")

        proof = []

        current_level = list(self.leaves)
        index = leaf_index

        while len(current_level) > 1:

            if len(current_level) % 2 != 0:
                current_level.append(current_level[-1])

            if index % 2 == 0:
                sibling_index = index + 1
                position = "right"
            else:
                sibling_index = index - 1
                position = "left"

            proof.append(
                {
                    "hash": current_level[sibling_index],
                    "position": position,
                }
            )

            next_level = []

            for i in range(0, len(current_level), 2):
                next_level.append(
                    self.hash_pair(
                        current_level[i],
                        current_level[i + 1],
                    )
                )

            index //= 2
            current_level = next_level

        return proof

    # ========================================================
    # VERIFY PROOF
    # ========================================================

    @staticmethod
    def verify_proof(
        leaf: str,
        proof: list[dict],
        expected_root: str,
    ) -> bool:
        """
        Verify a Merkle inclusion proof.
        """

        current = leaf

        for step in proof:

            sibling = step["hash"]
            position = step["position"]

            if position == "right":
                current = MerkleTree.hash_pair(
                    current,
                    sibling,
                )

            elif position == "left":
                current = MerkleTree.hash_pair(
                    sibling,
                    current,
                )

            else:
                return False

        return current == expected_root


# ============================================================
# SELF TEST
# ============================================================

def self_test() -> None:

    print("=" * 60)
    print("NEXCHAIN MERKLE TREE TEST")
    print("=" * 60)

    transactions = [
        double_sha256(b"transaction-1"),
        double_sha256(b"transaction-2"),
        double_sha256(b"transaction-3"),
        double_sha256(b"transaction-4"),
    ]

    tree = MerkleTree(transactions)

    root = tree.get_root()

    assert len(root) == 64

    print()
    print("[PASS] Merkle tree construction")
    print(f"[PASS] Merkle root: {root}")

    # --------------------------------------------------------
    # Proof
    # --------------------------------------------------------

    leaf_index = 2

    proof = tree.generate_proof(leaf_index)

    assert len(proof) == 2

    print("[PASS] Merkle proof generation")

    # --------------------------------------------------------
    # Verification
    # --------------------------------------------------------

    verified = MerkleTree.verify_proof(
        transactions[leaf_index],
        proof,
        root,
    )

    assert verified

    print("[PASS] Merkle proof verification")

    # --------------------------------------------------------
    # Tamper test
    # --------------------------------------------------------

    tampered_leaf = double_sha256(
        b"tampered transaction"
    )

    verified = MerkleTree.verify_proof(
        tampered_leaf,
        proof,
        root,
    )

    assert not verified

    print("[PASS] Merkle tamper detection")

    print()
    print("=" * 60)
    print("ALL MERKLE TESTS PASSED")
    print("=" * 60)


if __name__ == "__main__":
    self_test()