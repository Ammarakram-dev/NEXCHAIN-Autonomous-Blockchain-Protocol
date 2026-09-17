import {
  Activity,
  ArrowUpRight,
  Blocks,
  Box,
  CheckCircle2,
  ChevronRight,
  CircleDollarSign,
  Cpu,
  Database,
  Globe2,
  Layers3,
  Menu,
  Network,
  RefreshCw,
  Search,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
  X,
  Zap,
} from "lucide-react";

import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useState } from "react";

import BlockchainScene from "./components/scene/BlockchainScene";
import NetworkBackground from "./components/scene/NetworkBackground";
import { nexchainAPI } from "./lib/api";

const navItems = [
  { id: "overview", label: "Overview", icon: Activity },
  { id: "blocks", label: "Explorer", icon: Blocks },
  { id: "network", label: "Network", icon: Network },
  { id: "protocol", label: "Protocol", icon: Layers3 },
];

function formatNumber(value) {
  if (value === null || value === undefined) return "—";

  return new Intl.NumberFormat("en-US", {
    maximumFractionDigits: 4,
  }).format(Number(value));
}

function shorten(value, start = 8, end = 6) {
  if (!value) return "—";

  if (value.length <= start + end + 3) {
    return value;
  }

  return `${value.slice(0, start)}…${value.slice(-end)}`;
}

function formatTimestamp(timestamp) {
  if (!timestamp) return "—";

  const date = new Date(Number(timestamp) * 1000);

  if (Number.isNaN(date.getTime())) return "—";

  return date.toLocaleString();
}

function StatCard({
  icon: Icon,
  label,
  value,
  detail,
  accent = "purple",
}) {
  return (
    <motion.div
      className={`stat-card stat-${accent}`}
      initial={{ opacity: 0, y: 18 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      whileHover={{
        y: -5,
        transition: { duration: 0.2 },
      }}
    >
      <div className="stat-top">
        <div className="stat-icon">
          <Icon size={18} />
        </div>

        <span>{label}</span>
      </div>

      <div className="stat-value">
        {value}
      </div>

      {detail && (
        <div className="stat-detail">
          {detail}
        </div>
      )}
    </motion.div>
  );
}

function SectionHeader({
  eyebrow,
  title,
  description,
  action,
}) {
  return (
    <div className="section-header">
      <div>
        <div className="section-eyebrow">
          <span />
          {eyebrow}
        </div>

        <h2>{title}</h2>

        {description && (
          <p>{description}</p>
        )}
      </div>

      {action}
    </div>
  );
}

function StatusBadge({ online }) {
  return (
    <div className={`status-badge ${online ? "online" : "offline"}`}>
      <span className="status-dot" />
      {online ? "NETWORK ONLINE" : "NETWORK OFFLINE"}
    </div>
  );
}

function LoadingState() {
  return (
    <div className="loading-state">
      <div className="loader-ring" />
      <span>Synchronizing NEXCHAIN telemetry…</span>
    </div>
  );
}

function ErrorState({ message, onRetry }) {
  return (
    <div className="error-state">
      <ShieldCheck size={22} />
      <div>
        <strong>API connection unavailable</strong>
        <span>{message}</span>
      </div>

      <button
        className="ghost-button"
        onClick={onRetry}
      >
        <RefreshCw size={15} />
        Retry
      </button>
    </div>
  );
}

function Overview({
  health,
  status,
  blocks,
  onRefresh,
}) {
  const latestBlock = blocks?.blocks?.[0];

  const blockchain = status?.blockchain || {};
  const state = status?.state || {};
  const consensus = status?.consensus?.consensus || {};
  const mempool = status?.mempool || {};
  const protocol = status?.protocol || {};

  return (
    <div className="page-stack">
      <section className="hero">
        <div className="hero-copy">
          <motion.div
            className="hero-kicker"
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
          >
            <Sparkles size={15} />
            AUTONOMOUS BLOCKCHAIN PROTOCOL
          </motion.div>

          <motion.h1
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.1 }}
          >
            The infrastructure layer
            <br />
            for <span>autonomous value.</span>
          </motion.h1>

          <motion.p
            className="hero-description"
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.2 }}
          >
            NEXCHAIN is a programmable blockchain protocol
            engineered around verifiable state, persistent
            storage, consensus, secure transactions and
            autonomous execution.
          </motion.p>

          <motion.div
            className="hero-actions"
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.3 }}
          >
            <StatusBadge online={health?.ok === true} />

            <button
              className="refresh-button"
              onClick={onRefresh}
            >
              <RefreshCw size={15} />
              Sync network
            </button>
          </motion.div>
        </div>

        <div className="hero-visual">
          <BlockchainScene />

          <div className="scene-label scene-label-a">
            <span>STATE ROOT</span>
            <strong>
              {shorten(health?.state_root, 7, 5)}
            </strong>
          </div>

          <div className="scene-label scene-label-b">
            <span>CONSENSUS</span>
            <strong>ACTIVE</strong>
          </div>

          <div className="scene-label scene-label-c">
            <span>PROTOCOL</span>
            <strong>NEX / V1</strong>
          </div>
        </div>
      </section>

      <section className="stats-grid">
        <StatCard
          icon={Blocks}
          label="BLOCK HEIGHT"
          value={formatNumber(health?.height)}
          detail="Canonical chain height"
          accent="cyan"
        />

        <StatCard
          icon={CircleDollarSign}
          label="NEX SUPPLY"
          value={formatNumber(state.total_supply)}
          detail={`Max ${formatNumber(state.max_supply)}`}
          accent="purple"
        />

        <StatCard
          icon={Server}
          label="VALIDATORS"
          value={formatNumber(consensus.total_validators)}
          detail={`${formatNumber(consensus.active_validators)} active`}
          accent="indigo"
        />

        <StatCard
          icon={Zap}
          label="MEMPOOL"
          value={formatNumber(mempool.size)}
          detail={`${formatNumber(mempool.remaining_capacity)} slots available`}
          accent="blue"
        />
      </section>

      <section className="dashboard-grid">
        <motion.div
          className="panel"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">
                LATEST BLOCK
              </span>

              <h3>
                Block #{latestBlock?.height ?? health?.height ?? 0}
              </h3>
            </div>

            <Blocks size={20} />
          </div>

          <div className="data-list">
            <DataRow
              label="Block Hash"
              value={shorten(latestBlock?.block_hash)}
              mono
            />

            <DataRow
              label="Previous Hash"
              value={shorten(latestBlock?.previous_hash)}
              mono
            />

            <DataRow
              label="Validator"
              value={shorten(latestBlock?.validator)}
              mono
            />

            <DataRow
              label="Transactions"
              value={latestBlock?.transactions?.length ?? 0}
            />

            <DataRow
              label="Timestamp"
              value={formatTimestamp(latestBlock?.timestamp)}
            />
          </div>
        </motion.div>

        <motion.div
          className="panel"
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
        >
          <div className="panel-heading">
            <div>
              <span className="panel-kicker">
                PROTOCOL INTEGRITY
              </span>

              <h3>Runtime diagnostics</h3>
            </div>

            <ShieldCheck size={20} />
          </div>

          <div className="integrity-grid">
            <IntegrityItem
              label="Blockchain"
              value="VERIFIED"
            />

            <IntegrityItem
              label="State"
              value="VERIFIED"
            />

            <IntegrityItem
              label="Consensus"
              value="VERIFIED"
            />

            <IntegrityItem
              label="Storage"
              value="VERIFIED"
            />
          </div>

          <div className="integrity-seal">
            <div className="seal-icon">
              <CheckCircle2 size={26} />
            </div>

            <div>
              <strong>
                Integrity seal valid
              </strong>

              <span>
                NEXCHAIN runtime is reporting a verified
                protocol state.
              </span>
            </div>
          </div>
        </motion.div>
      </section>

      <section className="wide-panel">
        <div className="wide-panel-header">
          <div>
            <span className="panel-kicker">
              LIVE TELEMETRY
            </span>

            <h3>Network state</h3>
          </div>

          <div className="telemetry-live">
            <span />
            LIVE
          </div>
        </div>

        <div className="telemetry-grid">
          <Telemetry
            label="State Root"
            value={shorten(state.state_root, 10, 8)}
          />

          <Telemetry
            label="Protocol Hash"
            value={shorten(protocol.protocol_hash, 10, 8)}
          />

          <Telemetry
            label="Integrity Seal"
            value={shorten(protocol.integrity_seal, 10, 8)}
          />

          <Telemetry
            label="Network"
            value={health?.network || "NEXCHAIN"}
          />

          <Telemetry
            label="Token"
            value={health?.token || "NEX"}
          />

          <Telemetry
            label="Contracts"
            value={formatNumber(status?.contracts?.contracts)}
          />

          <Telemetry
            label="Storage Items"
            value={formatNumber(status?.contracts?.storage_items)}
          />

          <Telemetry
            label="Audit Records"
            value={formatNumber(protocol.audit_records)}
          />
        </div>
      </section>
    </div>
  );
}

function DataRow({ label, value, mono = false }) {
  return (
    <div className="data-row">
      <span>{label}</span>
      <strong className={mono ? "mono" : ""}>
        {value ?? "—"}
      </strong>
    </div>
  );
}

function IntegrityItem({ label, value }) {
  return (
    <div className="integrity-item">
      <div className="integrity-check">
        <CheckCircle2 size={16} />
      </div>

      <div>
        <span>{label}</span>
        <strong>{value}</strong>
      </div>
    </div>
  );
}

function Telemetry({ label, value }) {
  return (
    <div className="telemetry-item">
      <span>{label}</span>
      <strong className="mono">
        {value || "—"}
      </strong>
    </div>
  );
}

function Explorer({ blocks, status }) {
  const list = blocks?.blocks || [];

  return (
    <div className="page-stack">
      <SectionHeader
        eyebrow="CHAIN EXPLORER"
        title="Blockchain explorer"
        description="Inspect the canonical NEXCHAIN chain and its persisted block data."
        action={
          <div className="explorer-counter">
            <Blocks size={16} />
            {list.length} visible block{list.length !== 1 ? "s" : ""}
          </div>
        }
      />

      <div className="explorer-overview">
        <div className="explorer-metric">
          <span>HEIGHT</span>
          <strong>{formatNumber(status?.height)}</strong>
        </div>

        <div className="explorer-metric">
          <span>BLOCKS</span>
          <strong>{formatNumber(status?.blocks)}</strong>
        </div>

        <div className="explorer-metric">
          <span>TRANSACTIONS</span>
          <strong>{formatNumber(status?.blockchain?.transactions)}</strong>
        </div>

        <div className="explorer-metric">
          <span>MEMPOOL</span>
          <strong>{formatNumber(status?.mempool?.size)}</strong>
        </div>
      </div>

      <div className="block-list">
        {list.map((block, index) => (
          <motion.div
            className="block-card"
            key={block.block_hash || index}
            initial={{ opacity: 0, x: -18 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{
              delay: index * 0.05,
            }}
          >
            <div className="block-number">
              <span>BLOCK</span>
              <strong>
                #{block.height}
              </strong>
            </div>

            <div className="block-main">
              <div className="block-hash">
                <span>HASH</span>
                <strong className="mono">
                  {shorten(block.block_hash, 15, 10)}
                </strong>
              </div>

              <div className="block-meta">
                <span>
                  <Cpu size={14} />
                  {shorten(block.validator)}
                </span>

                <span>
                  <Activity size={14} />
                  {block.transactions?.length ?? 0} TX
                </span>

                <span>
                  <Database size={14} />
                  {formatTimestamp(block.timestamp)}
                </span>
              </div>
            </div>

            <div className="block-arrow">
              <ArrowUpRight size={19} />
            </div>
          </motion.div>
        ))}

        {list.length === 0 && (
          <div className="empty-state">
            No blocks returned by the NEXCHAIN API.
          </div>
        )}
      </div>
    </div>
  );
}

function NetworkPage({ status, health }) {
  const consensus =
    status?.consensus?.consensus || {};

  const validator =
    status?.validator ||
    status?.consensus?.validator ||
    "—";

  return (
    <div className="page-stack">
      <SectionHeader
        eyebrow="NETWORK INTELLIGENCE"
        title="NEXCHAIN network"
        description="Consensus, validator and runtime information exposed by the live protocol."
      />

      <div className="network-hero">
        <div className="network-orbit">
          <div className="network-core">
            <Network size={34} />
            <strong>NEX</strong>
            <span>NETWORK</span>
          </div>

          <div className="orbit orbit-one" />
          <div className="orbit orbit-two" />
          <div className="orbit orbit-three" />
        </div>

        <div className="network-summary">
          <StatusBadge online={health?.ok === true} />

          <h3>
            Autonomous consensus
            <br />
            <span>operating normally.</span>
          </h3>

          <p>
            The current runtime exposes a live validator,
            persistent state and consensus subsystem through
            the NEXCHAIN protocol API.
          </p>

          <div className="validator-chip">
            <Cpu size={15} />

            <div>
              <span>ACTIVE VALIDATOR</span>
              <strong className="mono">
                {shorten(validator, 13, 10)}
              </strong>
            </div>
          </div>
        </div>
      </div>

      <div className="network-grid">
        <NetworkCard
          icon={Server}
          title="Validators"
          value={consensus.total_validators}
          detail="Registered validators"
        />

        <NetworkCard
          icon={Zap}
          title="Active set"
          value={consensus.active_validators}
          detail="Currently active"
        />

        <NetworkCard
          icon={CircleDollarSign}
          title="Total stake"
          value={formatNumber(consensus.total_stake)}
          detail="Consensus stake"
        />

        <NetworkCard
          icon={Blocks}
          title="Committed"
          value={status?.consensus?.committed_blocks}
          detail="Committed blocks"
        />
      </div>
    </div>
  );
}

function NetworkCard({
  icon: Icon,
  title,
  value,
  detail,
}) {
  return (
    <motion.div
      className="network-card"
      whileHover={{
        y: -4,
      }}
    >
      <div className="network-card-icon">
        <Icon size={20} />
      </div>

      <span>{title}</span>

      <strong>
        {value ?? "—"}
      </strong>

      <small>{detail}</small>
    </motion.div>
  );
}

function ProtocolPage({ status }) {
  const protocol = status?.protocol || {};
  const contracts = status?.contracts || {};
  const state = status?.state || {};
  const mempool = status?.mempool || {};

  return (
    <div className="page-stack">
      <SectionHeader
        eyebrow="PROTOCOL CORE"
        title="Runtime architecture"
        description="A live technical view of the NEXCHAIN protocol subsystems."
      />

      <div className="architecture">
        <ArchitectureNode
          icon={Globe2}
          title="NEXCHAIN"
          subtitle="Protocol layer"
          active
        />

        <ChevronRight className="architecture-arrow" />

        <ArchitectureNode
          icon={Blocks}
          title="Blockchain"
          subtitle={`${status?.blocks ?? 0} blocks`}
          active
        />

        <ChevronRight className="architecture-arrow" />

        <ArchitectureNode
          icon={Database}
          title="State"
          subtitle={`${state.accounts ?? 0} accounts`}
          active
        />

        <ChevronRight className="architecture-arrow" />

        <ArchitectureNode
          icon={Zap}
          title="Consensus"
          subtitle={`${status?.consensus?.committed_blocks ?? 0} committed`}
          active
        />
      </div>

      <div className="protocol-grid">
        <ProtocolCard
          title="Protocol"
          icon={Terminal}
          items={[
            ["Version", protocol.version],
            ["Height", protocol.height],
            ["Transactions", protocol.transactions],
            ["Contracts", protocol.contracts],
            ["Finalized Height", protocol.finalized_height],
          ]}
        />

        <ProtocolCard
          title="State engine"
          icon={Database}
          items={[
            ["Accounts", state.accounts],
            ["Non-zero Accounts", state.nonzero_accounts],
            ["Total Supply", formatNumber(state.total_supply)],
            ["Maximum Supply", formatNumber(state.max_supply)],
            ["State Root", shorten(state.state_root, 12, 8)],
          ]}
        />

        <ProtocolCard
          title="Mempool"
          icon={Activity}
          items={[
            ["Pending", mempool.size],
            ["Capacity", mempool.capacity],
            ["Rejected", mempool.rejected],
            ["Removed", mempool.removed],
            ["Min Fee", mempool.min_fee],
          ]}
        />

        <ProtocolCard
          title="Contracts"
          icon={Box}
          items={[
            ["Contracts", contracts.contracts],
            ["Receipts", contracts.receipts],
            ["Storage Items", contracts.storage_items],
            ["Version", contracts.version],
            ["Contract Root", shorten(contracts.state_root, 12, 8)],
          ]}
        />
      </div>

      <div className="protocol-seal">
        <div className="protocol-seal-icon">
          <ShieldCheck size={28} />
        </div>

        <div>
          <span>INTEGRITY SEAL</span>
          <strong className="mono">
            {protocol.integrity_seal || "—"}
          </strong>
        </div>
      </div>
    </div>
  );
}

function ArchitectureNode({
  icon: Icon,
  title,
  subtitle,
  active,
}) {
  return (
    <motion.div
      className={`architecture-node ${
        active ? "active" : ""
      }`}
      whileHover={{
        scale: 1.035,
      }}
    >
      <Icon size={21} />
      <strong>{title}</strong>
      <span>{subtitle}</span>
    </motion.div>
  );
}

function ProtocolCard({
  icon: Icon,
  title,
  items,
}) {
  return (
    <motion.div
      className="protocol-card"
      whileHover={{ y: -4 }}
    >
      <div className="protocol-card-title">
        <div>
          <Icon size={19} />
        </div>

        <h3>{title}</h3>
      </div>

      <div className="protocol-items">
        {items.map(([label, value]) => (
          <div
            className="protocol-item"
            key={label}
          >
            <span>{label}</span>

            <strong className={
              String(value || "").length > 18
                ? "mono"
                : ""
            }>
              {value ?? "—"}
            </strong>
          </div>
        ))}
      </div>
    </motion.div>
  );
}

function App() {
  const [activePage, setActivePage] =
    useState("overview");

  const [health, setHealth] = useState(null);
  const [status, setStatus] = useState(null);
  const [blocks, setBlocks] = useState(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [mobileMenu, setMobileMenu] = useState(false);
  const [lastSync, setLastSync] = useState(null);
  const [search, setSearch] = useState("");

  const loadData = useCallback(async () => {
    try {
      setError(null);

      const [healthData, statusData, blocksData] =
        await Promise.all([
          nexchainAPI.health(),
          nexchainAPI.status(),
          nexchainAPI.blocks(),
        ]);

      setHealth(healthData);
      setStatus(statusData);
      setBlocks(blocksData);
      setLastSync(new Date());
    } catch (err) {
      setError(
        err?.message ||
          "Unable to communicate with NEXCHAIN."
      );
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();

    const interval = setInterval(
      loadData,
      10000
    );

    return () => clearInterval(interval);
  }, [loadData]);

  const filteredPage = useMemo(() => {
    const query = search.trim().toLowerCase();

    if (!query) return activePage;

    if (
      query.includes("block") ||
      query.includes("explorer")
    ) {
      return "blocks";
    }

    if (
      query.includes("network") ||
      query.includes("validator")
    ) {
      return "network";
    }

    if (
      query.includes("protocol") ||
      query.includes("state")
    ) {
      return "protocol";
    }

    return activePage;
  }, [search, activePage]);

  const navigate = (page) => {
    setActivePage(page);
    setSearch("");
    setMobileMenu(false);
  };

  return (
    <div className="app-shell">
      <NetworkBackground />

      <div className="ambient ambient-one" />
      <div className="ambient ambient-two" />

      <header className="topbar">
        <button
          className="brand"
          onClick={() => navigate("overview")}
        >
          <div className="brand-mark">
            <span />
            <span />
            <span />
          </div>

          <div>
            <strong>NEXCHAIN</strong>
            <small>AUTONOMOUS PROTOCOL</small>
          </div>
        </button>

        <nav className="desktop-nav">
          {navItems.map((item) => {
            const Icon = item.icon;

            return (
              <button
                key={item.id}
                className={
                  activePage === item.id
                    ? "nav-active"
                    : ""
                }
                onClick={() =>
                  navigate(item.id)
                }
              >
                <Icon size={15} />
                {item.label}
              </button>
            );
          })}
        </nav>

        <div className="topbar-actions">
          <div className="search-box">
            <Search size={15} />

            <input
              value={search}
              onChange={(event) =>
                setSearch(event.target.value)
              }
              placeholder="Explore protocol..."
            />
          </div>

          <div className="top-network">
            <span />
            MAIN NETWORK
          </div>

          <button
            className="mobile-menu-button"
            onClick={() =>
              setMobileMenu((value) => !value)
            }
          >
            {mobileMenu ? (
              <X size={20} />
            ) : (
              <Menu size={20} />
            )}
          </button>
        </div>
      </header>

      <AnimatePresence>
        {mobileMenu && (
          <motion.div
            className="mobile-nav"
            initial={{
              opacity: 0,
              height: 0,
            }}
            animate={{
              opacity: 1,
              height: "auto",
            }}
            exit={{
              opacity: 0,
              height: 0,
            }}
          >
            {navItems.map((item) => {
              const Icon = item.icon;

              return (
                <button
                  key={item.id}
                  onClick={() =>
                    navigate(item.id)
                  }
                >
                  <Icon size={17} />
                  {item.label}
                </button>
              );
            })}
          </motion.div>
        )}
      </AnimatePresence>

      <main className="main-content">
        <div className="page-status">
          <div>
            <span className="breadcrumb">
              NEXCHAIN /{" "}
              {
                navItems.find(
                  (item) =>
                    item.id === activePage
                )?.label
              }
            </span>
          </div>

          <div className="sync-status">
            <span
              className={
                health?.ok
                  ? "sync-dot"
                  : "sync-dot offline"
              }
            />

            {lastSync
              ? `SYNCED ${lastSync.toLocaleTimeString()}`
              : "CONNECTING…"}
          </div>
        </div>

        {loading ? (
          <LoadingState />
        ) : error ? (
          <ErrorState
            message={error}
            onRetry={loadData}
          />
        ) : (
          <>
            {filteredPage === "overview" && (
              <Overview
                health={health}
                status={status}
                blocks={blocks}
                onRefresh={loadData}
              />
            )}

            {filteredPage === "blocks" && (
              <Explorer
                blocks={blocks}
                status={status}
              />
            )}

            {filteredPage === "network" && (
              <NetworkPage
                status={status}
                health={health}
              />
            )}

            {filteredPage === "protocol" && (
              <ProtocolPage
                status={status}
              />
            )}
          </>
        )}
      </main>

      <footer className="footer">
        <div>
          <strong>NEXCHAIN</strong>
          <span>
            Autonomous Blockchain Protocol
          </span>
        </div>

        <div className="footer-right">
          <span>
            {health?.network || "NEXCHAIN"}
          </span>

          <span>•</span>

          <span>
            Protocol v
            {status?.protocol_version ?? 1}
          </span>

          <span>•</span>

          <span>
            {health?.ok
              ? "Integrity verified"
              : "Disconnected"}
          </span>
        </div>
      </footer>
    </div>
  );
}

export default App;