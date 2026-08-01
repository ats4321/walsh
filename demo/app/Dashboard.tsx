"use client";

import { useState } from "react";
import type { TickerRun, AgentThesis } from "./page";

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

const TICKER_LABEL: Record<string, string> = {
  AAPL: "AAPL — baseline",
  MSFT: "MSFT — baseline",
  NVDA: "NVDA — baseline",
  TSLA: "TSLA — tech vs fundamental disagreement",
  META: "META — risk veto (volatility)",
};

// Scale signal color by confidence: brighter/more saturated = higher conviction.
// Tiers: <60% → muted, 60-75% → standard, 75%+ → deep/saturated.
function cardSignalColor(signal: string, confidence: number): string {
  const up = signal === "STRONG_BUY" || signal === "BUY";
  const down = signal === "STRONG_SELL" || signal === "SELL";
  if (!up && !down) return "#94a3b8";
  if (up) {
    if (confidence >= 0.75) return "#16a34a";
    if (confidence >= 0.60) return "#22c55e";
    return "#4ade80";
  }
  if (confidence >= 0.75) return "#dc2626";
  if (confidence >= 0.60) return "#ef4444";
  return "#fca5a5";
}

const S = {
  page: { maxWidth: 960, margin: "0 auto", padding: "40px 24px" } as const,
  header: { marginBottom: 20 } as const,
  title: { fontSize: 28, fontWeight: 700, margin: 0, letterSpacing: "-0.5px" } as const,
  sub: { fontSize: 14, color: "#64748b", marginTop: 6 } as const,
  select: {
    background: "#1e1e24", border: "1px solid #2d2d36", color: "#e2e8f0",
    padding: "10px 16px", borderRadius: 8, fontSize: 15, cursor: "pointer",
    outline: "none", marginBottom: 32, width: 240,
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
  bnahSharpe: "2.86",
  maxDD: "−13.50%",
  winRate: "76.2%",
  trades: "21",
  period: "AAPL · MSFT · NVDA | Jan 2023 – Dec 2023",
};

// ponytail: hardcoded from actual backtest output; regenerate with backtest/engine.py if data changes
const EQUITY_WALSH = [100.0, 104.5, 108.2, 113.5, 117.8, 122.0, 126.4, 132.1, 138.5, 131.2, 126.8, 155.2, 175.5];
const EQUITY_BNH   = [100.0, 113.0, 122.0, 146.6, 152.9, 181.5, 197.6, 201.2, 208.1, 187.7, 190.7, 216.7, 219.8];
const EQUITY_LABELS = ["Jan 1", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function EquityCurve() {
  const VW = 560, VH = 190, PL = 44, PR = 16, PT = 14, PB = 36;
  const cw = VW - PL - PR, ch = VH - PT - PB;
  const n = EQUITY_WALSH.length;
  const yMin = 88, yMax = 232, yRange = yMax - yMin;

  const px = (i: number) => PL + (i / (n - 1)) * cw;
  const py = (v: number) => PT + (1 - (v - yMin) / yRange) * ch;
  const pts = (arr: number[]) => arr.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");

  // Polygon tracing BnH forward then Walsh backward — shades the underperformance gap.
  const gapPolygon = [
    ...EQUITY_BNH.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`),
    ...[...EQUITY_WALSH].reverse().map((v, i) => `${px(n - 1 - i).toFixed(1)},${py(v).toFixed(1)}`),
  ].join(" ");

  const gridYs = [100, 125, 150, 175, 200];
  const showLabel = [0, 3, 6, 9, 12];

  return (
    <div>
      <svg viewBox={`0 0 ${VW} ${VH}`} style={{ display: "block", width: "100%", height: "auto", overflow: "visible" }}>
        {gridYs.map(v => (
          <line key={v} x1={PL} x2={VW - PR} y1={py(v).toFixed(1)} y2={py(v).toFixed(1)}
            stroke="#2d2d36" strokeWidth={1} />
        ))}
        {[100, 150, 200].map(v => (
          <text key={v} x={PL - 6} y={(py(v) + 4).toFixed(1)}
            textAnchor="end" fontSize={12} fill="#475569">{v}%</text>
        ))}
        {showLabel.map(i => (
          <text key={i} x={px(i).toFixed(1)} y={VH - 10}
            textAnchor="middle" fontSize={12} fill="#475569">{EQUITY_LABELS[i]}</text>
        ))}
        {/* Shaded gap between B&H and Walsh — makes underperformance magnitude obvious at a glance */}
        <polygon points={gapPolygon} fill="rgba(239,68,68,0.10)" />
        <polyline points={pts(EQUITY_BNH)} fill="none" stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 3" />
        <polyline points={pts(EQUITY_WALSH)} fill="none" stroke="#6366f1" strokeWidth={2} />
        <circle cx={px(n - 1).toFixed(1)} cy={py(EQUITY_WALSH[n - 1]).toFixed(1)} r={3} fill="#6366f1" />
        <circle cx={px(n - 1).toFixed(1)} cy={py(EQUITY_BNH[n - 1]).toFixed(1)} r={3} fill="#64748b" />
      </svg>
      <div style={{ display: "flex", gap: 18, justifyContent: "center", marginTop: 6, flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8" }}>
          <svg width={20} height={10} style={{ display: "block", flexShrink: 0 }}>
            <line x1={0} y1={5} x2={20} y2={5} stroke="#6366f1" strokeWidth={2} />
          </svg>
          Walsh (+75.5%)
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8" }}>
          <svg width={20} height={10} style={{ display: "block", flexShrink: 0 }}>
            <line x1={0} y1={5} x2={20} y2={5} stroke="#64748b" strokeWidth={1.5} strokeDasharray="4 3" />
          </svg>
          B&amp;H (+119.8%)
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 11, color: "#94a3b8" }}>
          <svg width={14} height={10} style={{ display: "block", flexShrink: 0 }}>
            <rect width={14} height={10} fill="rgba(239,68,68,0.18)" />
          </svg>
          Gap (−44 pp)
        </span>
      </div>
    </div>
  );
}

function ConfBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={S.confBar}>
      <div style={{ height: "100%", width: `${Math.round(value * 100)}%`, borderRadius: 2, background: color, opacity: 0.7 }} />
    </div>
  );
}

function AgentCard({ thesis }: { thesis: AgentThesis }) {
  const color = cardSignalColor(thesis.signal, thesis.confidence);
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

function LimitationsBanner() {
  const [open, setOpen] = useState(false);
  const bannerBase = {
    background: "rgba(234,179,8,0.08)", border: "1px solid rgba(234,179,8,0.3)",
    borderRadius: 8, marginBottom: 24, fontSize: 13, color: "#ca8a04", lineHeight: 1.55,
  };
  return (
    <div style={bannerBase}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 8, width: "100%",
          background: "none", border: "none", cursor: "pointer", color: "#ca8a04",
          fontSize: 13, fontWeight: 600, padding: "10px 16px", textAlign: "left",
        }}
      >
        <span>⚠️ Known limitation: underperforms buy-and-hold by ~44pp</span>
        <span style={{ marginLeft: "auto", fontSize: 11, fontWeight: 400, color: "#a16207" }}>
          {open ? "▲ collapse" : "▼ expand"}
        </span>
      </button>
      {open && (
        <div style={{ padding: "0 16px 12px", color: "#a16207" }}>
          The Jan–Dec 2023 backtest returned +75.5% vs +119.8% passive buy-and-hold on AAPL/MSFT/NVDA,
          underperforming by ~44 pp. The primary cause is that the volatility damper (vol_cap=40%) zeroed
          out NVDA allocation — the period's biggest winner — while the mean-reversion agent added
          conflicting SELL signals in a one-directional trend year. Signal weighting needs tuning before
          this strategy is suitable for live deployment. The immediate next step is replacing the hard
          vol_cap=40% binary cutoff in RiskManager.adjust() with continuous position-size scaling —
          linearly reducing allocation as volatility rises past a threshold, rather than zeroing it out entirely.
        </div>
      )}
    </div>
  );
}

function SummaryStrip({ run }: { run: TickerRun }) {
  const signalColor = cardSignalColor(run.signal, run.confidence);
  // One-line reason: first sentence of reasoning or risk_notes for vetoed
  const reason = (!run.approved ? run.risk_notes : run.reasoning).split(".")[0] + ".";
  return (
    <div style={{
      display: "flex", alignItems: "center", flexWrap: "wrap", gap: "12px 20px",
      background: "#1a1a22", border: "1px solid #2d2d36", borderRadius: 10,
      padding: "14px 20px", marginBottom: 24,
    }}>
      <span style={{ fontSize: 20, fontWeight: 700, color: "#e2e8f0", letterSpacing: "-0.3px" }}>
        {run.ticker}
      </span>
      <span style={{
        fontSize: 15, fontWeight: 700, color: signalColor,
        background: `${signalColor}1a`, border: `1px solid ${signalColor}44`,
        borderRadius: 6, padding: "2px 10px",
      }}>
        {run.signal.replace("_", " ")}
      </span>
      <span style={{
        fontSize: 12, fontWeight: 600,
        background: run.approved ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
        color: run.approved ? "#22c55e" : "#ef4444",
        border: `1px solid ${run.approved ? "rgba(34,197,94,0.3)" : "rgba(239,68,68,0.3)"}`,
        borderRadius: 5, padding: "2px 8px",
      }}>
        {run.approved ? "✅ Approved" : "🚫 Vetoed"}
      </span>
      <span style={{ fontSize: 12, color: "#64748b", flex: "1 1 200px" }}>{reason}</span>
    </div>
  );
}

export default function Dashboard({ runs, tickers }: { runs: Record<string, TickerRun>; tickers: string[] }) {
  const [ticker, setTicker] = useState(tickers[0]);
  const run = runs[ticker];
  const finalSignalColor = cardSignalColor(run.signal, run.confidence);

  return (
    <div style={S.page}>
      <div style={S.header}>
        <h1 style={S.title}>Walsh Demo</h1>
        <p style={S.sub}>Multi-agent stock research pipeline · Pre-generated runs (no live API calls)</p>
      </div>

      <LimitationsBanner />

      <select
        style={S.select}
        value={ticker}
        onChange={(e) => setTicker(e.target.value)}
      >
        {tickers.map((t) => (
          <option key={t} value={t}>{TICKER_LABEL[t] ?? t}</option>
        ))}
      </select>

      {/* Summary strip: most important info above the analyst cards */}
      <SummaryStrip run={run} />

      {/* Agent theses */}
      <div style={S.grid}>
        {run.theses.map((t) => <AgentCard key={t.agent} thesis={t} />)}
      </div>

      {/* Portfolio Manager */}
      <div style={S.section}>
        <p style={S.sectionTitle}>🧠 Portfolio Manager Synthesis</p>
        <div style={{ fontSize: 14, color: "#94a3b8", lineHeight: 1.6 }}>{run.reasoning}</div>
      </div>

      {/* Risk Manager */}
      <div style={S.section}>
        <p style={S.sectionTitle}>🛡️ Risk Manager Decision</p>
        <div style={S.verdict(run.approved)}>
          {run.approved ? "✅ APPROVED" : "🚫 VETOED"} &nbsp;·&nbsp; Final signal:{" "}
          <span style={{ color: finalSignalColor }}>{run.signal.replace("_", " ")}</span>
        </div>
        <div style={{ fontSize: 14, color: "#94a3b8" }}>{run.risk_notes}</div>
      </div>

      {/* Backtest panel */}
      <div style={S.section}>
        <p style={S.sectionTitle}>
          📉 Backtest Results
          <span style={S.badge(false)}>REAL DATA</span>
        </p>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: -8, marginBottom: 4 }}>
          Fixed universe: AAPL · MSFT · NVDA — these numbers do not change with the ticker selected above.
        </p>
        <p style={{ fontSize: 12, color: "#64748b", marginTop: 0, marginBottom: 16 }}>
          {BACKTEST.period} · <strong style={{ color: "#475569" }}>Rule-based approximation</strong> — the backtest
          uses deterministic SMA/momentum/mean-reversion agents, not the LLM-powered agents shown in the cards above.
          Results represent the algorithmic signal engine only.
        </p>

        <div style={{ marginBottom: 20 }}>
          <EquityCurve />
          <p style={{ fontSize: 10, color: "#475569", margin: "6px 0 0", textAlign: "center" }}>
            Portfolio value (% of initial $100k) · Jan – Dec 2023 · monthly snapshots
          </p>
        </div>

        <div style={S.metricGrid}>
          <div style={S.metric}>
            <div style={S.metricLabel}>Sharpe Ratio</div>
            {/* Value is neutral — comparison badge shows the underperformance in context */}
            <div style={{ ...S.metricValue, color: "#e2e8f0" }}>{BACKTEST.sharpe}</div>
            <div style={S.metricSub}>
              vs {BACKTEST.bnahSharpe} B&amp;H{" "}
              <span style={{ color: "#f87171", fontSize: 10, fontWeight: 600 }}>−0.5</span>
            </div>
          </div>
          <div style={S.metric}>
            <div style={S.metricLabel}>Total Return</div>
            {/* Positive number shown neutral — red is reserved for the vs-B&H delta badge below */}
            <div style={{ ...S.metricValue, color: "#e2e8f0" }}>{BACKTEST.walshReturn}</div>
            <div style={S.metricSub}>
              vs {BACKTEST.bnahReturn} B&amp;H{" "}
              <span style={{ color: "#f87171", fontSize: 10, fontWeight: 600 }}>−44.2pp</span>
            </div>
          </div>
          <div style={S.metric}>
            <div style={S.metricLabel}>Win Rate</div>
            <div style={{ ...S.metricValue, color: "#22c55e" }}>{BACKTEST.winRate}</div>
            <div style={S.metricSub}>{BACKTEST.trades} trades · Max DD {BACKTEST.maxDD}</div>
          </div>
        </div>
        <p style={{ fontSize: 11, color: "#475569", marginTop: 16, marginBottom: 0 }}>
          Per-agent calibration metrics pending ≥50 completed LLM-backed pipeline runs.
        </p>
      </div>
    </div>
  );
}
