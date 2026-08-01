"use client";

import { useState } from "react";
import type { TickerRun, AgentThesis } from "./page";

const SIGNAL_COLOR: Record<string, string> = {
  STRONG_BUY: "#22c55e",
  BUY: "#86efac",
  HOLD: "#94a3b8",
  SELL: "#f87171",
  STRONG_SELL: "#ef4444",
};

const AGENT_LABEL: Record<string, string> = {
  fundamental: "Fundamental Analyst",
  technical: "Technical Analyst",
  sentiment: "Sentiment Analyst",
  macro: "Macro Analyst",
};

const AGENT_ICON: Record<string, string> = {
  fundamental: "📊",
  technical: "📈",
  sentiment: "🗞️",
  macro: "🌍",
};

const S = {
  page: { maxWidth: 960, margin: "0 auto", padding: "40px 24px" } as const,
  header: { marginBottom: 32 } as const,
  title: { fontSize: 28, fontWeight: 700, margin: 0, letterSpacing: "-0.5px" } as const,
  sub: { fontSize: 14, color: "#64748b", marginTop: 6 } as const,
  select: {
    background: "#1e1e24", border: "1px solid #2d2d36", color: "#e2e8f0",
    padding: "10px 16px", borderRadius: 8, fontSize: 16, cursor: "pointer",
    outline: "none", marginBottom: 32, width: 200,
  } as const,
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))", gap: 16, marginBottom: 32 } as const,
  card: { background: "#1a1a22", borderRadius: 12, padding: "20px 20px 16px", border: "1px solid #2d2d36" } as const,
  cardAgent: { fontSize: 12, color: "#64748b", marginBottom: 4 } as const,
  cardSignal: { fontSize: 22, fontWeight: 700, marginBottom: 4 } as const,
  cardConf: { fontSize: 13, color: "#94a3b8", marginBottom: 10 } as const,
  cardReason: { fontSize: 12, color: "#94a3b8", lineHeight: 1.5 } as const,
  section: { background: "#1a1a22", borderRadius: 12, padding: "24px", border: "1px solid #2d2d36", marginBottom: 20 } as const,
  sectionTitle: { fontSize: 13, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: 1, color: "#64748b", marginBottom: 16, marginTop: 0 } as const,
  verdict: (approved: boolean) => ({
    display: "inline-flex", alignItems: "center", gap: 8,
    padding: "6px 14px", borderRadius: 20, fontSize: 15, fontWeight: 600,
    background: approved ? "rgba(34,197,94,0.15)" : "rgba(239,68,68,0.15)",
    color: approved ? "#22c55e" : "#ef4444",
    border: `1px solid ${approved ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
    marginBottom: 12,
  }),
  metricGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 16 } as const,
  metric: { background: "#0f0f11", borderRadius: 8, padding: "16px" } as const,
  metricLabel: { fontSize: 11, color: "#64748b", textTransform: "uppercase" as const, letterSpacing: 0.5 } as const,
  metricValue: { fontSize: 22, fontWeight: 700, marginTop: 4 } as const,
  metricSub: { fontSize: 12, color: "#64748b", marginTop: 2 } as const,
  badge: (pending: boolean) => ({
    display: "inline-block", fontSize: 10, fontWeight: 600,
    background: pending ? "rgba(234,179,8,0.15)" : "rgba(34,197,94,0.15)",
    color: pending ? "#eab308" : "#22c55e",
    border: `1px solid ${pending ? "rgba(234,179,8,0.3)" : "rgba(34,197,94,0.3)"}`,
    padding: "2px 6px", borderRadius: 4, marginLeft: 6, verticalAlign: "middle",
  }),
  confBar: { height: 4, borderRadius: 2, background: "#2d2d36", marginTop: 8 } as const,
};

const BACKTEST = {
  walshReturn: "75.52%",
  bnahReturn: "119.75%",
  sharpe: "2.36",
  maxDD: "−13.50%",
  winRate: "76.2%",
  trades: "21",
  period: "AAPL · MSFT · NVDA | Jan 2023 – Dec 2023",
};

function ConfBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={S.confBar}>
      <div style={{ height: "100%", width: `${Math.round(value * 100)}%`, borderRadius: 2, background: color, opacity: 0.7 }} />
    </div>
  );
}

function AgentCard({ thesis }: { thesis: AgentThesis }) {
  const color = SIGNAL_COLOR[thesis.signal] ?? "#94a3b8";
  return (
    <div style={S.card}>
      <div style={S.cardAgent}>{AGENT_ICON[thesis.agent] ?? "🤖"} {AGENT_LABEL[thesis.agent] ?? thesis.agent}</div>
      <div style={{ ...S.cardSignal, color }}>{thesis.signal.replace("_", " ")}</div>
      <div style={S.cardConf}>{Math.round(thesis.confidence * 100)}% confidence</div>
      <ConfBar value={thesis.confidence} color={color} />
      <div style={{ ...S.cardReason, marginTop: 10 }}>{thesis.reasoning}</div>
    </div>
  );
}

export default function Dashboard({ runs, tickers }: { runs: Record<string, TickerRun>; tickers: string[] }) {
  const [ticker, setTicker] = useState(tickers[0]);
  const run = runs[ticker];
  const color = SIGNAL_COLOR[run.signal] ?? "#94a3b8";

  return (
    <div style={S.page}>
      <div style={S.header}>
        <h1 style={S.title}>Walsh Demo</h1>
        <p style={S.sub}>Multi-agent stock research pipeline · Pre-generated runs (no live API calls)</p>
      </div>

      <select
        style={S.select}
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
      >
        {tickers.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>

      {/* Agent theses */}
      <div style={S.grid}>
        {run.theses.map((t) => <AgentCard key={t.agent} thesis={t} />)}
      </div>

      {/* Portfolio Manager */}
      <div style={S.section}>
        <p style={S.sectionTitle}>Portfolio Manager Synthesis</p>
        <div style={{ fontSize: 14, color: "#94a3b8", lineHeight: 1.6 }}>{run.reasoning}</div>
      </div>

      {/* Risk Manager */}
      <div style={S.section}>
        <p style={S.sectionTitle}>Risk Manager Decision</p>
        <div style={S.verdict(run.approved)}>
          {run.approved ? "✅ APPROVED" : "🚫 VETOED"} &nbsp;·&nbsp; Final signal: {" "}
          <span style={{ color }}>{run.signal.replace("_", " ")}</span>
        </div>
        <div style={{ fontSize: 14, color: "#94a3b8" }}>{run.risk_notes}</div>
      </div>

      {/* Backtest panel */}
      <div style={S.section}>
        <p style={S.sectionTitle}>
          Backtest Results
          <span style={S.badge(false)}>REAL</span>
        </p>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: -8, marginBottom: 20 }}>{BACKTEST.period} · Rule-based agents · No look-ahead</p>
        <div style={S.metricGrid}>
          <div style={S.metric}>
            <div style={S.metricLabel}>Sharpe Ratio</div>
            <div style={S.metricValue}>{BACKTEST.sharpe}</div>
            <div style={S.metricSub}>vs {" "}
              <span style={{ color: "#ef4444" }}>2.86</span> buy-and-hold</div>
          </div>
          <div style={S.metric}>
            <div style={S.metricLabel}>Total Return</div>
            <div style={{ ...S.metricValue, color: "#22c55e" }}>{BACKTEST.walshReturn}</div>
            <div style={S.metricSub}>vs {" "}
              <span style={{ color: "#22c55e" }}>{BACKTEST.bnahReturn}</span> buy-and-hold</div>
          </div>
          <div style={S.metric}>
            <div style={S.metricLabel}>Win Rate</div>
            <div style={{ ...S.metricValue, color: "#22c55e" }}>{BACKTEST.winRate}</div>
            <div style={S.metricSub}>{BACKTEST.trades} trades · Max DD {BACKTEST.maxDD}</div>
          </div>
        </div>
        <p style={{ fontSize: 11, color: "#475569", marginTop: 16, marginBottom: 0 }}>
          Per-agent accuracy and confidence calibration metrics are pending a longer eval run. Agent attribution requires ≥50 complete runs to produce meaningful calibration curves.
        </p>
      </div>
    </div>
  );
}
