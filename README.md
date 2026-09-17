<div align="center">

# ⛓️ NEXCHAIN

### ⚡ AUTONOMOUS BLOCKCHAIN PROTOCOL

<img src="https://capsule-render.vercel.app/api?type=waving&height=180&color=0:050816,50:111827,100:312e81&text=NEXCHAIN&fontColor=ffffff&fontSize=58&fontAlignY=40&desc=Autonomous%20Blockchain%20Protocol&descAlignY=63&descSize=18&animation=fadeIn" width="100%"/>

<br/>

<img src="https://readme-typing-svg.demolab.com?font=JetBrains+Mono&weight=600&size=18&duration=2800&pause=900&color=8B5CF6&center=true&vCenter=true&width=850&lines=Consensus+%E2%80%A2+P2P+Networking+%E2%80%A2+Smart+Contracts;Cryptography+%E2%80%A2+Persistent+State+%E2%80%A2+Transaction+Engine;Built+from+Scratch+%E2%80%A2+Modular+%E2%80%A2+Extensible+%E2%80%A2+Protocol-First" />

<br/><br/>

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![React](https://img.shields.io/badge/React-UI-61DAFB?style=for-the-badge&logo=react&logoColor=111827)](https://react.dev/)
[![Vite](https://img.shields.io/badge/Vite-Frontend-646CFF?style=for-the-badge&logo=vite&logoColor=white)](https://vite.dev/)
[![SQLite](https://img.shields.io/badge/SQLite-Persistence-003B57?style=for-the-badge&logo=sqlite&logoColor=white)](https://sqlite.org/)
[![Git](https://img.shields.io/badge/Git-Version_Control-F05032?style=for-the-badge&logo=git&logoColor=white)](https://git-scm.com/)
[![License](https://img.shields.io/badge/License-MIT-22C55E?style=for-the-badge)](LICENSE)

<br/>

### `PROTOCOL STATUS`

🟢 **CORE READY** &nbsp;·&nbsp;
🟢 **CONSENSUS READY** &nbsp;·&nbsp;
🟢 **STATE READY** &nbsp;·&nbsp;
🟢 **STORAGE READY** &nbsp;·&nbsp;
🟢 **API READY** &nbsp;·&nbsp;
🟢 **FRONTEND READY**

<br/>

</div>

---

<div align="center">

## ◈ THE NETWORK LAYER BETWEEN IDEA & EXECUTION ◈

**NEXCHAIN** is a modular blockchain protocol engineered from the ground up around
**consensus, cryptography, transactions, persistent state, networking, execution,
and observability**.

</div>

<br/>

---

# ✦ SYSTEM OVERVIEW

```text
                         ┌───────────────────────────┐
                         │       NEXCHAIN UI         │
                         │      React + Vite         │
                         └─────────────┬─────────────┘
                                       │
                                  HTTP / JSON
                                       │
                         ┌─────────────▼─────────────┐
                         │        API GATEWAY         │
                         │       Python Server        │
                         └─────────────┬─────────────┘
                                       │
                         ┌─────────────▼─────────────┐
                         │      NEXCHAIN RUNTIME      │
                         │     Protocol Coordinator   │
                         └─────────────┬─────────────┘
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
 ┌─────────────────┐         ┌─────────────────┐          ┌─────────────────┐
 │    CONSENSUS    │         │     STATE       │          │    MEMPOOL      │
 │   Validation    │         │  Account State  │          │  Transactions   │
 └────────┬────────┘         └────────┬────────┘          └────────┬────────┘
          │                           │                            │
          └───────────────────────────┼────────────────────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │     BLOCKCHAIN CORE     │
                         │ Blocks + Transactions  │
                         └────────────┬────────────┘
                                      │
                         ┌────────────▼────────────┐
                         │      PERSISTENCE        │
                         │   SQLite State Layer    │
                         └─────────────────────────┘
⚡ CORE CAPABILITIES
<table> <tr> <td width="50%">
⛓️ Blockchain Core
Block construction
Chain validation
Block hashing
Previous-hash linking
Merkle-root support
Chain integrity verification
</td> <td width="50%">
🧠 Consensus
Validator identity
Block validation
Consensus execution
Integrity verification
Runtime consensus integration
</td> </tr> <tr> <td>
🔐 Cryptography
Transaction signing
Public-key handling
Hash-based integrity
Cryptographic verification
</td> <td>
💾 Persistent State
Account state
State roots
SQLite persistence
Snapshot support
State verification
Recovery-oriented storage
</td> </tr> <tr> <td>
📦 Transaction Engine
Transaction structure
Nonce handling
Fees
Sender / recipient flow
Mempool management
Validation pipeline
</td> <td>
🌐 Networking
Network abstraction
Peer-oriented architecture
Protocol communication layer
API exposure
Future multi-node expansion
</td> </tr> <tr> <td>
🧩 Smart Contracts
Virtual-machine layer
Contract execution architecture
Extensible execution model
Protocol-level integration
</td> <td>
📊 Observability
Runtime status
Chain height
State root
Mempool state
Health endpoint
Integrated self-tests
</td> </tr> </table>
◈ ARCHITECTURE
NEXCHAIN
│
├── api/
│   └── HTTP API + protocol endpoints
│
├── cli/
│   └── Command-line interaction layer
│
├── consensus/
│   └── Consensus and validation logic
│
├── core/
│   ├── Runtime
│   ├── Blockchain
│   ├── Blocks
│   ├── Transactions
│   ├── Mempool
│   └── Block production
│
├── crypto/
│   └── Cryptographic primitives
│
├── data/
│   └── Runtime blockchain/state databases
│
├── network/
│   └── P2P/networking abstractions
│
├── storage/
│   ├── Blockchain persistence
│   └── State persistence
│
├── vm/
│   └── Smart-contract execution layer
│
├── frontend/
│   ├── React
│   ├── Vite
│   ├── Protocol dashboard
│   └── API integration
│
├── config.py
├── main.py
├── fix_db.py
└── requirements.txt
🔥 PROTOCOL FLOW
                 TRANSACTION
                      │
                      ▼
              ┌───────────────┐
              │   VALIDATION  │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │    MEMPOOL    │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │    CONSENSUS  │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ BLOCK CREATION│
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │ STATE UPDATE  │
              └───────┬───────┘
                      │
                      ▼
              ┌───────────────┐
              │   PERSISTENCE │
              └───────┬───────┘
                      │
                      ▼
                 NEW STATE
🧬 DATA INTEGRITY

Every block participates in a cryptographically linked chain:

┌──────────────────────┐
│ BLOCK #0000          │
│                      │
│ Previous: GENESIS    │
│ Hash: A91F...        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ BLOCK #0001          │
│                      │
│ Previous: A91F...    │
│ Hash: 73BD...        │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│ BLOCK #0002          │
│                      │
│ Previous: 73BD...    │
│ Hash: C42A...        │
└──────────┬───────────┘
           │
           ▼
        CONTINUITY

A change to historical block data propagates through the integrity chain,
making unauthorized modification detectable.

🧠 STATE ENGINE

NEXCHAIN separates blockchain history from current protocol state.

                 BLOCKCHAIN
                     │
              Historical Data
                     │
                     ▼
              ┌─────────────┐
              │ State Engine │
              └──────┬──────┘
                     │
          ┌──────────┼──────────┐
          ▼          ▼          ▼
       Accounts    Nonces      Root
          │          │          │
          └──────────┼──────────┘
                     ▼
              Persistent State

The state layer supports:

account persistence
balance tracking
state roots
snapshots
verification
replacement
database recovery
integrity testing
🌐 API

NEXCHAIN exposes a local HTTP API for the frontend and external clients.

Health
GET /api/v1/health
Protocol Status
GET /api/v1/status
Blocks
GET /api/v1/blocks
Integrated Self-Test
POST /api/v1/self-test
Local API
http://127.0.0.1:8080
🖥️ FRONTEND

The NEXCHAIN interface is built using:

React
   │
   ├── Protocol Dashboard
   ├── Runtime Status
   ├── Chain Information
   ├── Network State
   ├── API Connectivity
   └── Live Protocol Data
          │
          ▼
      NEXCHAIN API

Development server:

http://127.0.0.1:5173
🚀 QUICK START
1. Clone
git clone https://github.com/Ammarakram-dev/NEXCHAIN-Autonomous-Blockchain-Protocol.git
cd NEXCHAIN-Autonomous-Blockchain-Protocol
2. Install Python Dependencies
py -m pip install -r requirements.txt
3. Verify the Protocol
py main.py

Expected result:

======================================================================
NEXCHAIN — INTEGRATED PROTOCOL
======================================================================

Runtime initialized successfully.

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
🌐 START THE API

Open Terminal 1:

cd /d/NEXCHAIN
py -m api.server

API:

http://127.0.0.1:8080
🎛️ START THE FRONTEND

Open Terminal 2:

cd /d/NEXCHAIN/frontend
npm install
npm run dev

Open:

http://127.0.0.1:5173
🏗️ PRODUCTION BUILD
cd /d/NEXCHAIN/frontend
npm run build

The generated production bundle is placed inside:

frontend/dist/
🔎 API VERIFICATION
Health
cd /d/NEXCHAIN

py -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/health').read().decode())"
Status
py -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/status').read().decode())"
Blocks
py -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/api/v1/blocks').read().decode())"
🧪 INTEGRITY VERIFICATION

NEXCHAIN contains integrated verification across the major protocol layers.

             ┌─────────────────────┐
             │   INTEGRITY TEST    │
             └──────────┬──────────┘
                        │
        ┌───────────────┼────────────────┐
        ▼               ▼                ▼
   Blockchain         State          Consensus
        │               │                │
        └───────────────┼────────────────┘
                        ▼
                  Storage Layer
                        │
                        ▼
                   Protocol
                        │
                        ▼
                    OVERALL

Run:

py main.py

The runtime verifies:

blockchain
state
consensus
blockchain storage
state storage
protocol integration
overall runtime integrity
💾 PERSISTENCE

NEXCHAIN uses SQLite-backed persistence for local protocol state.

data/
│
├── blockchain state
│
└── protocol state

Runtime databases are intentionally excluded from version control.

This keeps the source repository clean while allowing each runtime environment
to maintain its own persistent state.

🔐 SECURITY MODEL

NEXCHAIN is designed around layered integrity:

TRANSACTION
     │
     ▼
SIGNATURE
     │
     ▼
VALIDATION
     │
     ▼
MEMPOOL
     │
     ▼
CONSENSUS
     │
     ▼
BLOCK HASH
     │
     ▼
STATE ROOT
     │
     ▼
PERSISTENT STORAGE

The architecture keeps cryptography, validation, consensus, state,
and persistence as distinct protocol layers.

🧩 DESIGN PRINCIPLES
Principle	Implementation
Modular	Independent protocol packages
Deterministic	Structured validation pipeline
Persistent	SQLite-backed state
Verifiable	Integrated integrity tests
Extensible	VM, networking and API layers
Observable	Runtime and health endpoints
Developer-Friendly	Python + React architecture
Protocol-First	Core logic independent from UI
🛠️ TECHNOLOGY STACK
<div align="center">
Layer	Technology
Protocol	Python
API	Python HTTP server
Frontend	React
Build System	Vite
Persistence	SQLite
Cryptography	Python cryptographic layer
Version Control	Git
Runtime	Local / extensible node architecture
</div>
📡 NETWORK ARCHITECTURE

The networking layer is designed for future multi-node protocol operation.

                   ┌──────────────┐
                   │    NODE A    │
                   └──────┬───────┘
                          │
                    P2P NETWORK
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐
       │  NODE B  │ │  NODE C  │ │  NODE D  │
       └──────────┘ └──────────┘ └──────────┘

The current repository provides the protocol foundation for extending the
system toward multi-node deployment.

🤖 SMART CONTRACT LAYER

NEXCHAIN includes a dedicated VM layer for programmable execution.

CONTRACT
   │
   ▼
┌───────────────┐
│ VM EXECUTION  │
└───────┬───────┘
        │
        ▼
   STATE CHANGE
        │
        ▼
   PERSISTENCE

The separation allows execution logic to evolve independently from the
blockchain core.

📦 PROJECT STRUCTURE
NEXCHAIN/
│
├── api/
├── cli/
├── consensus/
├── core/
├── crypto/
├── data/
├── network/
├── storage/
├── vm/
│
├── frontend/
│
├── config.py
├── fix_db.py
├── main.py
├── requirements.txt
├── README.md
└── .gitignore
🧭 DEVELOPMENT ROADMAP
CORE PROTOCOL
     │
     ├── Blockchain              ✓
     ├── Transactions            ✓
     ├── State Engine            ✓
     ├── Consensus               ✓
     ├── Persistence             ✓
     ├── API                     ✓
     └── Frontend                ✓
     
NEXT PROTOCOL EXPANSION
     │
     ├── Multi-node networking
     ├── Peer discovery
     ├── Production node hosting
     ├── Testnet infrastructure
     ├── Advanced smart contracts
     ├── Wallet integration
     └── Public network deployment
⚠️ DEVELOPMENT / DEPLOYMENT NOTE

The repository currently provides a functioning local protocol implementation
with an integrated frontend and API.

A truly public blockchain network additionally requires infrastructure such as:

PUBLIC HTTPS API
       │
       ▼
PUBLIC NODE
       │
       ▼
MULTIPLE PEERS
       │
       ▼
NETWORK CONSENSUS
       │
       ▼
PERSISTENT PRODUCTION STORAGE

Localhost development is intentionally separated from public deployment.

🧪 DEVELOPMENT STATUS
<div align="center">
NEXCHAIN v1.1.0
┌─────────────────────────────────────────────────────┐
│                                                     │
│   ███████╗███████╗██████╗ ███████╗ █████╗ ██╗     │
│   ██╔════╝██╔════╝██╔══██╗██╔════╝██╔══██╗██║     │
│   █████╗  █████╗  ██████╔╝█████╗  ███████║██║     │
│   ██╔══╝  ██╔══╝  ██╔═══╝ ██╔══╝  ██╔══██║██║     │
│   ██║     ███████╗██║     ███████╗██║  ██║███████╗│
│   ╚═╝     ╚══════╝╚═╝     ╚══════╝╚═╝  ╚═╝╚══════╝│
│                                                     │
│             AUTONOMOUS BLOCKCHAIN                  │
│                                                     │
└─────────────────────────────────────────────────────┘

CORE · CONSENSUS · STATE · STORAGE · API · UI

</div>
👨‍💻 AUTHOR
<div align="center">
Ammar Akram

Software Engineering · AI/ML · Blockchain · Python

<br/>

</div>
📜 LICENSE

This project is released under the MIT License.

See LICENSE for details.

<div align="center"> <img src="https://capsule-render.vercel.app/api?type=waving&height=140&section=footer&color=0:312e81,50:111827,100:050816&animation=fadeIn"/>
⛓️ NEXCHAIN

BUILD THE PROTOCOL. VERIFY THE STATE. EXTEND THE NETWORK.

<br/>

████████████████████████████████████████

<br/>

⭐ Star the repository if you want to follow the protocol's evolution.

</div> ```
