<div align="center">

# ⚡ NEXCHAIN

### Autonomous Blockchain Protocol

<p>
  <strong>A blockchain protocol engineered from the ground up for transparent state, deterministic execution, persistent storage, consensus, networking, and real-time protocol visualization.</strong>
</p>

<br>

<img src="https://img.shields.io/badge/NEXCHAIN-v1.0.0-7C3AED?style=for-the-badge&logo=bitcoin&logoColor=white" />
<img src="https://img.shields.io/badge/Protocol-Autonomous-06B6D4?style=for-the-badge" />
<img src="https://img.shields.io/badge/Language-Python-3776AB?style=for-the-badge&logo=python&logoColor=white" />
<img src="https://img.shields.io/badge/Frontend-React-61DAFB?style=for-the-badge&logo=react&logoColor=black" />
<img src="https://img.shields.io/badge/Build-Vite-646CFF?style=for-the-badge&logo=vite&logoColor=white" />
<img src="https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge" />

<br><br>

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:0F172A,50:312E81,100:06B6D4&height=180&section=header&text=NEXCHAIN&fontSize=55&fontColor=ffffff&animation=fadeIn&fontAlignY=35&desc=Autonomous%20Blockchain%20Protocol&descAlignY=58&descSize=18" width="100%" />

</div>

---

## ◈ What is NEXCHAIN?

**NEXCHAIN** is an independently engineered blockchain protocol designed around a modular architecture rather than a single monolithic application.

It combines:

- ⛓️ Blockchain construction
- 🧠 Consensus execution
- 🔐 Cryptographic transaction handling
- 🌳 Merkle/state verification
- 💾 Persistent blockchain storage
- 💾 Persistent state storage
- 🌐 Network and synchronization components
- ⚙️ Smart-contract execution foundations
- 🚀 Protocol runtime orchestration
- 🖥️ Real-time web visualization
- 🔎 Blockchain explorer capabilities
- 🧪 Integrated integrity testing

The project is structured so that the protocol itself remains independent from the visual frontend.

```text
                         ┌───────────────────────────┐
                         │       NEXCHAIN WEB        │
                         │     React + Vite UI       │
                         └─────────────┬─────────────┘
                                       │
                                  HTTP / JSON
                                       │
                         ┌─────────────▼─────────────┐
                         │        NEXCHAIN API       │
                         │     Protocol Gateway      │
                         └─────────────┬─────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │     NEXCHAIN RUNTIME      │
                         │  Protocol Orchestration   │
                         └─────────────┬─────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              │                        │                        │
       ┌──────▼──────┐         ┌───────▼───────┐        ┌──────▼──────┐
       │ Blockchain  │         │    State      │        │  Consensus  │
       │    Core     │         │    Engine     │        │   Engine    │
       └──────┬──────┘         └───────┬───────┘        └──────┬──────┘
              │                        │                        │
              └────────────────────────┼────────────────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │        STORAGE LAYER      │
                         │ SQLite + Recovery + Root  │
                         └───────────────────────────┘
```

---

# ✦ Core Architecture

NEXCHAIN is divided into independent protocol domains.

### `core/`

The heart of the protocol.

Responsible for:

- Blocks
- Blockchain
- Transactions
- State
- Mempool
- Merkle structures
- Block production
- Contract state
- Contract VM
- Runtime orchestration
- Recovery
- Protocol core

---

### `consensus/`

Consensus execution layer.

```text
Consensus
   │
   ├── Validator logic
   ├── Block validation
   ├── Chain validation
   └── Consensus execution
```

---

### `crypto/`

Cryptographic primitives and protocol cryptography.

Used for secure transaction and protocol operations.

---

### `storage/`

Persistent protocol state.

```text
                    STORAGE
                       │
            ┌──────────┴──────────┐
            │                     │
      Blockchain Store       State Store
            │                     │
       Blocks / TXs          Accounts / Root
            │                     │
            └──────────┬──────────┘
                       │
                    SQLite
```

Features include:

- Persistent blocks
- Persistent transactions
- Persistent accounts
- State roots
- Supply tracking
- Integrity validation
- Snapshots
- Atomic replacement
- Restart recovery

---

### `network/`

Networking foundations for protocol nodes.

Includes:

- Node management
- Transport
- Synchronization
- Network state

---

### `vm/`

Virtual-machine foundation for executable blockchain logic and future smart-contract expansion.

---

### `api/`

Protocol-facing HTTP interface.

The frontend communicates with NEXCHAIN through this layer rather than directly manipulating internal blockchain objects.

---

### `cli/`

Command-line protocol interaction foundation.

---

# ⚡ Protocol Flow

```text
                  TRANSACTION
                       │
                       ▼
                 ┌───────────┐
                 │ Validation│
                 └─────┬─────┘
                       │
                       ▼
                  ┌─────────┐
                  │ Mempool │
                  └────┬────┘
                       │
                       ▼
               ┌───────────────┐
               │ Block Producer│
               └───────┬───────┘
                       │
                       ▼
                 ┌──────────┐
                 │  Block   │
                 └────┬─────┘
                      │
          ┌───────────┼───────────┐
          │           │           │
          ▼           ▼           ▼
      Consensus     State      Merkle
          │           │           │
          └───────────┼───────────┘
                      │
                      ▼
                Persistent DB
                      │
                      ▼
                 State Root
                      │
                      ▼
                 API / Explorer
```

---

# ◇ State Integrity

NEXCHAIN maintains a cryptographically verifiable state representation.

The state layer tracks:

- Account addresses
- Balances
- Nonces
- Total supply
- State root

Every persisted state can be reconstructed and verified after restart.

```text
Accounts
   │
   ▼
Deterministic State Representation
   │
   ▼
State Root
   │
   ├───────────────┐
   ▼               ▼
Persisted Root   Recomputed Root
   │               │
   └───────┬───────┘
           ▼
       Verification
```

A mismatch indicates that the persisted state does not correspond to the expected state representation.

---

# ⛓️ Persistent Blockchain

NEXCHAIN uses persistent SQLite storage for blockchain data.

The blockchain store maintains:

```text
Blocks
├── height
├── version
├── previous hash
├── timestamp
├── validator
├── nonce
├── difficulty
├── merkle root
├── block hash
└── state root
```

Transactions are persisted separately and linked to their corresponding block height.

---

# 💾 Persistent State

The persistent state store maintains:

```text
metadata
├── state_root
├── total_supply
└── schema_version

accounts
├── address
├── balance
└── nonce
```

The storage system supports:

- Save
- Load
- Verify
- Snapshot
- Replace
- Recovery
- Statistics
- Corruption detection

---

# 🛡️ Integrity Model

NEXCHAIN does not simply save data and assume that it is correct.

The storage layer validates:

```text
                    STATE
                      │
                      ▼
             ┌────────────────┐
             │ Account Checks  │
             └───────┬────────┘
                     │
                     ▼
             ┌────────────────┐
             │ Supply Checks  │
             └───────┬────────┘
                     │
                     ▼
             ┌────────────────┐
             │ State Root     │
             │ Calculation    │
             └───────┬────────┘
                     │
                     ▼
             ┌────────────────┐
             │ Persisted Root  │
             │ Comparison      │
             └───────┬────────┘
                     │
                     ▼
                  VERIFIED
```

---

# 🌐 NEXCHAIN Web Interface

The frontend provides a real-time protocol visualization layer.

Built with:

- React
- Vite
- Modern CSS
- Responsive layouts
- Animated protocol components
- API-driven state
- Explorer views

The interface is designed around the concept of a live blockchain command center.

### Frontend capabilities

```text
┌─────────────────────────────────────────────┐
│              NEXCHAIN PROTOCOL              │
├─────────────────────────────────────────────┤
│                                             │
│   NETWORK       BLOCK HEIGHT      STATE     │
│   ONLINE             0             ROOT     │
│                                             │
├─────────────────────────────────────────────┤
│                                             │
│             BLOCKCHAIN EXPLORER             │
│                                             │
│   BLOCKS      TRANSACTIONS      NETWORK     │
│                                             │
├─────────────────────────────────────────────┤
│                                             │
│              LIVE PROTOCOL STATUS           │
│                                             │
└─────────────────────────────────────────────┘
```

The frontend communicates with the backend through HTTP API endpoints.

---

# 🧩 Project Structure

```text
NEXCHAIN/
│
├── api/
│   └── ...
│
├── cli/
│   └── ...
│
├── consensus/
│   ├── __init__.py
│   └── engine.py
│
├── core/
│   ├── block.py
│   ├── block_producer.py
│   ├── blockchain.py
│   ├── consensus_chain.py
│   ├── contract_state.py
│   ├── contract_vm.py
│   ├── mempool.py
│   ├── merkle.py
│   ├── protocol_core.py
│   ├── recovery.py
│   ├── runtime.py
│   ├── state.py
│   ├── state_block.py
│   └── transaction.py
│
├── crypto/
│   └── crypto_engine.py
│
├── data/
│   └── ...
│
├── network/
│   ├── node.py
│   ├── sync.py
│   └── transport.py
│
├── storage/
│   ├── blockchain_store.py
│   ├── database.py
│   └── state_store.py
│
├── vm/
│   └── ...
│
├── frontend/
│   ├── src/
│   ├── public/
│   ├── package.json
│   ├── vite.config.*
│   └── ...
│
├── config.py
├── fix_db.py
├── main.py
├── requirements.txt
└── README.md
```

---

# 🚀 Run NEXCHAIN

## 1. Clone

```bash
git clone https://github.com/Ammarakram-dev/NEXCHAIN-Autonomous-Blockchain-Protocol.git
cd NEXCHAIN-Autonomous-Blockchain-Protocol
```

---

## 2. Run the protocol

```bash
py main.py
```

A successful runtime should display:

```text
======================================================================
NEXCHAIN — INTEGRATED PROTOCOL
======================================================================

Runtime initialized successfully.
Network : NEXCHAIN
Token   : NEX
Height  : 0
Validator: ...
State Root: ...

Running integrated integrity test...

[PASS] blockchain
[PASS] state
[PASS] consensus
[PASS] blockchain_storage
[PASS] state_storage
[PASS] protocol
[PASS] overall

======================================================================
NEXCHAIN INTEGRATED RUNTIME: READY
======================================================================
```

---

# 🧪 Protocol Testing

NEXCHAIN includes integrated integrity testing across the major protocol layers.

Run:

```bash
py main.py
```

The runtime performs integrated verification of:

```text
✓ Blockchain
✓ State
✓ Consensus
✓ Blockchain Storage
✓ State Storage
✓ Protocol
✓ Overall Runtime
```

---

# 💾 Storage Tests

### Blockchain storage

```bash
py -m storage.blockchain_store
```

### State storage

```bash
py -m storage.state_store
```

Successful state persistence verifies:

```text
✓ Database initialization
✓ State creation
✓ State persistence
✓ State recovery
✓ Root verification
✓ State modification
✓ Snapshot creation
✓ Atomic replacement
✓ Final integrity verification
```

---

# 🖥️ Frontend Development

Open a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite will provide a local development address similar to:

```text
http://127.0.0.1:5173/
```

---

# 🔌 Backend + Frontend

NEXCHAIN is designed as a two-layer application:

```text
                    USER
                     │
                     ▼
              ┌─────────────┐
              │   FRONTEND  │
              │ React / Vite│
              └──────┬──────┘
                     │
                  HTTP API
                     │
                     ▼
              ┌─────────────┐
              │   NEXCHAIN  │
              │     API     │
              └──────┬──────┘
                     │
                     ▼
              ┌─────────────┐
              │   RUNTIME   │
              └──────┬──────┘
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       BLOCKS      STATE     CONSENSUS
          │          │          │
          └──────────┼──────────┘
                     ▼
                 STORAGE
```

The frontend should be started alongside the API/backend service.

---

# 📡 API Layer

The protocol exposes API endpoints for frontend interaction.

Typical resources include:

```text
/api/v1/health
/api/v1/status
/api/v1/blocks
```

The API layer provides the bridge between the internal protocol runtime and external applications.

This architecture allows future clients to be built without modifying the blockchain core.

---

# 🔭 Explorer Architecture

The web interface can consume protocol information such as:

```text
Network Status
       │
       ├── Chain Height
       ├── Latest Block
       ├── Latest Hash
       ├── State Root
       ├── Validator
       ├── Mempool
       └── Network Health
```

This creates a foundation for a public blockchain explorer.

---

# 🧠 Design Philosophy

NEXCHAIN is built around several principles:

### Determinism

Protocol state should be reproducible from valid inputs.

### Modularity

Core components remain separated so that individual systems can evolve independently.

### Verifiability

Persisted state should be independently validated.

### Recoverability

Restarting the node should not destroy protocol state.

### Transparency

Protocol information should be observable through APIs and the web interface.

### Extensibility

The architecture leaves room for:

- Additional validators
- More advanced networking
- Smart contracts
- Wallet integration
- Token transfers
- Multi-node deployment
- Peer discovery
- Testnet environments
- Mainnet infrastructure

---

# ⚙️ Technology Stack

| Layer | Technology |
|---|---|
| Protocol | Python |
| Blockchain | Custom implementation |
| Consensus | Custom engine |
| Cryptography | Python cryptographic layer |
| Persistence | SQLite |
| API | Python HTTP/API layer |
| Frontend | React |
| Build System | Vite |
| Data Format | JSON / SQLite |
| Version Control | Git |
| Repository | GitHub |

---

# 📈 Development Roadmap

```text
                 NEXCHAIN EVOLUTION
                         │
                         ▼
              ┌────────────────────┐
              │   Protocol Core    │
              │        ✓           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Persistent Storage │
              │        ✓           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Runtime Integrity  │
              │        ✓           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Web Interface      │
              │        ✓           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Multi-Node Network │
              │        →           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Wallet Ecosystem   │
              │        →           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Public Testnet     │
              │        →           │
              └─────────┬──────────┘
                        │
                        ▼
              ┌────────────────────┐
              │ Production Network │
              │        →           │
              └────────────────────┘
```

---

# 🔐 Security Direction

Future security development can include:

- Stronger transaction signature verification
- Key management
- Replay protection
- Peer authentication
- Rate limiting
- API authentication
- Network-level protections
- Contract execution isolation
- Formal protocol testing
- Fuzz testing
- Adversarial consensus testing

---

# 🌍 Public Usage Vision

NEXCHAIN is structured so that users do not need to interact directly with internal Python modules.

The intended public interaction model is:

```text
                 NEXCHAIN
                     │
       ┌─────────────┼─────────────┐
       │             │             │
       ▼             ▼             ▼
     Wallet       Explorer        API
       │             │             │
       └─────────────┼─────────────┘
                     │
                     ▼
               NEXCHAIN Nodes
                     │
                     ▼
                 Blockchain
```

A future public deployment can expose the frontend through a domain while blockchain nodes operate independently behind the API/network layer.

---

# 🛠️ Development

Create a virtual environment:

```bash
py -m venv .venv
```

Activate on Windows:

```bash
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run the protocol:

```bash
py main.py
```

---

# 🧹 Git Hygiene

Generated Python cache files should not be committed.

Recommended `.gitignore` entries:

```gitignore
__pycache__/
*.py[cod]
*.pyo
.venv/
venv/
.env
*.log
dist/
node_modules/
```

Runtime databases may be excluded from future production repository versions depending on deployment strategy.

---

# 📦 Production Build

Build the frontend:

```bash
cd frontend
npm run build
```

The production bundle is generated inside:

```text
frontend/dist/
```

---

# 🔗 Repository

<div align="center">

### NEXCHAIN — Autonomous Blockchain Protocol

<a href="https://github.com/Ammarakram-dev/NEXCHAIN-Autonomous-Blockchain-Protocol">
  <img src="https://img.shields.io/badge/GitHub-Repository-111827?style=for-the-badge&logo=github&logoColor=white" />
</a>

<br><br>

**A blockchain protocol built from the ground up.**

</div>

---

# 📜 License

This project is released under the **MIT License**.

See the repository license file for the applicable terms.

---

<div align="center">

<img src="https://capsule-render.vercel.app/api?type=waving&color=0:06B6D4,50:312E81,100:0F172A&height=140&section=footer&animation=fadeIn" width="100%" />

### ⚡ NEXCHAIN

**BUILD · VERIFY · CONNECT · EVOLVE**

<br>

`NEXCHAIN v1.0.0`

<br>

<sub>Autonomous Blockchain Protocol</sub>

</div>