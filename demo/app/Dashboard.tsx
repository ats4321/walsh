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
  page: { maxWidth: 1000, margin: "0 auto", padding: "48px 24px" } as const,
  header: { marginBottom: 28 } as const,
  title: { fontSize: 30, fontWeight: 800, margin: 0, letterSpacing: "-1px", color: "#f1f5f9" } as const,
  sub: { fontSize: 13, color: "#475569", marginTop: 8, letterSpacing: "0.1px" } as const,
  divider: { height: 1, background: "#1e2030", margin: "20px 0 0" } as const,
  // Select is wrapped in a relative div; chevron is an overlay
  selectWrap: { position: "relative" as const, display: "inline-block", marginBottom: 32 } as const,
  select: {
    appearance: "none" as const,
    background: "#1a1a22", border: "1px solid #2d2d36", color: "#e2e8f0",
    padding: "10px 40px 10px 16px", borderRadius: 8, fontSize: 14, cursor: "pointer",
    outline: "none", width: 260,
    boxShadow: "0 1px 3px rgba(0,0,0,0.3)",
  } as const,
  grid: { display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(210px, 1fr))", gap: 16, marginBottom: 32 } as const,
  // Card base — top accent border set inline per signal color; hover handled by CSS class
  card: {
    background: "#1a1a22", borderRadius: 12, padding: "18px 20px 16px",
    border: "1px solid #2d2d36", borderTop: "2px solid transparent",
    cursor: "default",
  } as const,
  cardAgent: { fontSize: 11, color: "#64748b", marginBottom: 6, letterSpacing: "0.3px" } as const,
  cardSignal: { fontSize: 21, fontWeight: 800, marginBottom: 2, letterSpacing: "-0.5px" } as const,
  cardConf: { fontSize: 12, color: "#64748b", marginBottom: 8 } as const,
  cardReason: { fontSize: 11.5, color: "#64748b", lineHeight: 1.55 } as const,
  section: {
    background: "#1a1a22", borderRadius: 12, padding: "24px 28px",
    border: "1px solid #2d2d36", marginBottom: 16,
  } as const,
  sectionTitle: {
    fontSize: 11, fontWeight: 700, textTransform: "uppercase" as const,
    letterSpacing: 1.5, color: "#475569", marginBottom: 18, marginTop: 0,
    display: "flex", alignItems: "center", gap: 7,
  } as const,
  verdict: (approved: boolean) => ({
    display: "inline-flex", alignItems: "center", gap: 8,
    padding: "6px 14px", borderRadius: 20, fontSize: 14, fontWeight: 700,
    background: approved ? "rgba(34,197,94,0.12)" : "rgba(239,68,68,0.12)",
    color: approved ? "#22c55e" : "#ef4444",
    border: `1px solid ${approved ? "rgba(34,197,94,0.25)" : "rgba(239,68,68,0.25)"}`,
    marginBottom: 14, letterSpacing: "0.2px",
  }),
  metricGrid: { display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 } as const,
  metric: { background: "#0f0f13", borderRadius: 10, padding: "16px 18px", border: "1px solid #1e1e2a" } as const,
  metricLabel: { fontSize: 10, color: "#475569", textTransform: "uppercase" as const, letterSpacing: 1 } as const,
  metricValue: { fontSize: 24, fontWeight: 800, marginTop: 6, letterSpacing: "-0.5px" } as const,
  metricSub: { fontSize: 11, color: "#475569", marginTop: 4 } as const,
  badge: (pending: boolean) => ({
    display: "inline-block", fontSize: 9, fontWeight: 700, letterSpacing: 0.5,
    background: pending ? "rgba(234,179,8,0.12)" : "rgba(34,197,94,0.12)",
    color: pending ? "#ca8a04" : "#16a34a",
    border: `1px solid ${pending ? "rgba(234,179,8,0.25)" : "rgba(34,197,94,0.25)"}`,
    padding: "2px 7px", borderRadius: 4, marginLeft: 8, verticalAlign: "middle",
  }),
  confBar: { height: 5, borderRadius: 3, background: "#2a2a34", marginTop: 6 } as const,
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
            stroke="#1e2030" strokeWidth={1} />
        ))}
        {[100, 150, 200].map(v => (
          <text key={v} x={PL - 6} y={(py(v) + 4).toFixed(1)}
            textAnchor="end" fontSize={11} fill="#334155">{v}%</text>
        ))}
        {showLabel.map(i => (
          <text key={i} x={px(i).toFixed(1)} y={VH - 10}
            textAnchor="middle" fontSize={11} fill="#334155">{EQUITY_LABELS[i]}</text>
        ))}
        {/* Shaded gap between B&H and Walsh — makes underperformance magnitude obvious at a glance */}
        <polygon points={gapPolygon} fill="rgba(239,68,68,0.09)" />
        <polyline points={pts(EQUITY_BNH)} fill="none" stroke="#475569" strokeWidth={1.5} strokeDasharray="4 3" />
        <polyline points={pts(EQUITY_WALSH)} fill="none" stroke="#6366f1" strokeWidth={2} />
        <circle cx={px(n - 1).toFixed(1)} cy={py(EQUITY_WALSH[n - 1]).toFixed(1)} r={3.5} fill="#6366f1" />
        <circle cx={px(n - 1).toFixed(1)} cy={py(EQUITY_BNH[n - 1]).toFixed(1)} r={3.5} fill="#475569" />
      </svg>
      <div style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 10, flexWrap: "wrap" }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#64748b" }}>
          <svg width={20} height={8} style={{ display: "block", flexShrink: 0 }}>
            <line x1={0} y1={4} x2={20} y2={4} stroke="#6366f1" strokeWidth={2} />
          </svg>
          Walsh (+75.5%)
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#64748b" }}>
          <svg width={20} height={8} style={{ display: "block", flexShrink: 0 }}>
            <line x1={0} y1={4} x2={20} y2={4} stroke="#475569" strokeWidth={1.5} strokeDasharray="4 3" />
          </svg>
          B&amp;H (+119.8%)
        </span>
        <span style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "#64748b" }}>
          <svg width={14} height={8} style={{ display: "block", flexShrink: 0 }}>
            <rect width={14} height={8} rx={2} fill="rgba(239,68,68,0.18)" />
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
      <div style={{ height: "100%", width: `${Math.round(value * 100)}%`, borderRadius: 3, background: color, opacity: 0.75 }} />
    </div>
  );
}

function AgentCard({ thesis }: { thesis: AgentThesis }) {
  const [hovered, setHovered] = useState(false);
  const color = cardSignalColor(thesis.signal, thesis.confidence);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        ...S.card,
        borderTopColor: color,
        transform: hovered ? "translateY(-3px)" : "translateY(0)",
        boxShadow: hovered ? "0 10px 28px rgba(0,0,0,0.4)" : "0 1px 4px rgba(0,0,0,0.2)",
        transition: "transform 0.15s ease, box-shadow 0.15s ease",
      }}
    >
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
  return (
    <div style={{
      background: "rgba(234,179,8,0.06)", border: "1px solid rgba(234,179,8,0.22)",
      borderRadius: 9, marginBottom: 28, fontSize: 13, overflow: "hidden",
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 8, width: "100%",
          background: "none", border: "none", cursor: "pointer", color: "#b45309",
          fontSize: 13, fontWeight: 600, padding: "11px 16px", textAlign: "left",
        }}
      >
        <span style={{ flex: 1 }}>⚠️ Known limitation: underperforms buy-and-hold by ~44pp</span>
        <span style={{
          fontSize: 10, fontWeight: 500, color: "#92400e", letterSpacing: "0.3px",
          background: "rgba(234,179,8,0.12)", borderRadius: 4, padding: "2px 6px",
        }}>
          {open ? "▲ COLLAPSE" : "▼ EXPAND"}
        </span>
      </button>
      <div style={{
        maxHeight: open ? "200px" : "0",
        overflow: "hidden",
        transition: "max-height 0.22s ease",
      }}>
        <div style={{ padding: "0 16px 14px", fontSize: 12.5, color: "#92400e", lineHeight: 1.65 }}>
          The Jan–Dec 2023 backtest returned +75.5% vs +119.8% passive buy-and-hold on AAPL/MSFT/NVDA,
          underperforming by ~44 pp. The primary cause is that the volatility damper (vol_cap=40%) zeroed
          out NVDA allocation — the period's biggest winner — while the mean-reversion agent added
          conflicting SELL signals in a one-directional trend year. Signal weighting needs tuning before
          this strategy is suitable for live deployment. The immediate next step is replacing the hard
          vol_cap=40% binary cutoff in RiskManager.adjust() with continuous position-size scaling —
          linearly reducing allocation as volatility rises past a threshold, rather than zeroing it out entirely.
        </div>
      </div>
    </div>
  );
}

function SummaryStrip({ run }: { run: TickerRun }) {
  const signalColor = cardSignalColor(run.signal, run.confidence);
  // One-line reason: first sentence of reasoning or risk_notes for vetoed
  const reason = (!run.approved ? run.risk_notes : run.reasoning).split(".")[0] + ".";
  return (
    <div style={{
      display: "flex", alignItems: "center", flexWrap: "wrap", gap: "10px 16px",
      background: "#1a1a22",
      borderLeft: `3px solid ${signalColor}`,
      borderRadius: "0 10px 10px 0",
      border: "1px solid #2d2d36",
      borderLeftColor: signalColor,
      padding: "14px 20px",
      marginBottom: 28,
      boxShadow: `inset 3px 0 0 ${signalColor}`,
    }}>
      <span style={{ fontSize: 22, fontWeight: 800, color: "#f1f5f9", letterSpacing: "-0.5px" }}>
        {run.ticker}
      </span>
      <span style={{
        fontSize: 13, fontWeight: 700, color: signalColor,
        background: `${signalColor}18`, border: `1px solid ${signalColor}38`,
        borderRadius: 6, padding: "3px 10px", letterSpacing: "0.3px",
      }}>
        {run.signal.replace("_", " ")}
      </span>
      <span style={{
        fontSize: 11, fontWeight: 700, letterSpacing: "0.3px",
        background: run.approved ? "rgba(34,197,94,0.10)" : "rgba(239,68,68,0.10)",
        color: run.approved ? "#16a34a" : "#ef4444",
        border: `1px solid ${run.approved ? "rgba(34,197,94,0.22)" : "rgba(239,68,68,0.22)"}`,
        borderRadius: 5, padding: "3px 9px",
      }}>
        {run.approved ? "✅ Approved" : "🚫 Vetoed"}
      </span>
      <span style={{ fontSize: 12, color: "#475569", flex: "1 1 200px", lineHeight: 1.4 }}>{reason}</span>
    </div>
  );
}

// Chevron icon for the select wrapper
function Chevron() {
  return (
    <svg
      width={12} height={12} viewBox="0 0 12 12" fill="none"
      style={{ position: "absolute", right: 14, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}
    >
      <path d="M2 4l4 4 4-4" stroke="#475569" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
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
        <div style={S.divider} />
      </div>

      <LimitationsBanner />

      <div style={S.selectWrap}>
        <select
          style={S.select}
          value={ticker}
          onChange={(e) => setTicker(e.target.value)}
        >
          {tickers.map((t) => (
            <option key={t} value={t}>{TICKER_LABEL[t] ?? t}</option>
          ))}
        </select>
        <Chevron />
      </div>

      {/* Summary strip: most important info above the analyst cards */}
      <SummaryStrip run={run} />

      {/* Agent theses */}
      <div style={S.grid}>
        {run.theses.map((t) => <AgentCard key={t.agent} thesis={t} />)}
      </div>

      {/* Portfolio Manager */}
      <div style={S.section}>
        <p style={S.sectionTitle}>🧠 Portfolio Manager Synthesis</p>
        <div style={{ fontSize: 13.5, color: "#94a3b8", lineHeight: 1.65 }}>{run.reasoning}</div>
      </div>

      {/* Risk Manager */}
      <div style={S.section}>
        <p style={S.sectionTitle}>🛡️ Risk Manager Decision</p>
        <div style={S.verdict(run.approved)}>
          {run.approved ? "✅ APPROVED" : "🚫 VETOED"} &nbsp;·&nbsp; Final signal:{" "}
          <span style={{ color: finalSignalColor }}>{run.signal.replace("_", " ")}</span>
        </div>
        <div style={{ fontSize: 13.5, color: "#94a3b8", lineHeight: 1.65 }}>{run.risk_notes}</div>
      </div>

      {/* Backtest panel */}
      <div style={S.section}>
        <p style={S.sectionTitle}>
          📉 Backtest Results
          <span style={S.badge(false)}>REAL DATA</span>
        </p>
        <p style={{ fontSize: 12, color: "#475569", marginTop: -10, marginBottom: 4, lineHeight: 1.5 }}>
          Fixed universe: AAPL · MSFT · NVDA — these numbers do not change with the ticker selected above.
        </p>
        <p style={{ fontSize: 12, color: "#475569", marginTop: 0, marginBottom: 20, lineHeight: 1.5 }}>
          {BACKTEST.period} · <strong style={{ color: "#64748b" }}>Rule-based approximation</strong> — the backtest
          uses deterministic SMA/momentum/mean-reversion agents, not the LLM-powered agents shown in the cards above.
          Results represent the algorithmic signal engine only.
        </p>

        <div style={{ marginBottom: 24 }}>
          <EquityCurve />
          <p style={{ fontSize: 10, color: "#334155", margin: "8px 0 0", textAlign: "center", letterSpacing: "0.2px" }}>
            Portfolio value (% of initial $100k) · Jan – Dec 2023 · monthly snapshots
          </p>
        </div>

        <div style={S.metricGrid}>
          <div style={S.metric}>
            <div style={S.metricLabel}>Sharpe Ratio</div>
            <div style={{ ...S.metricValue, color: "#e2e8f0" }}>{BACKTEST.sharpe}</div>
            <div style={S.metricSub}>
              vs {BACKTEST.bnahSharpe} B&amp;H{" "}
              <span style={{ color: "#f87171", fontSize: 10, fontWeight: 700 }}>−0.5</span>
            </div>
          </div>
          <div style={S.metric}>
            <div style={S.metricLabel}>Total Return</div>
            {/* Positive number shown neutral — red is reserved for the vs-B&H delta badge */}
            <div style={{ ...S.metricValue, color: "#e2e8f0" }}>{BACKTEST.walshReturn}</div>
            <div style={S.metricSub}>
              vs {BACKTEST.bnahReturn} B&amp;H{" "}
              <span style={{ color: "#f87171", fontSize: 10, fontWeight: 700 }}>−44.2pp</span>
            </div>
          </div>
          <div style={S.metric}>
            <div style={S.metricLabel}>Win Rate</div>
            <div style={{ ...S.metricValue, color: "#22c55e" }}>{BACKTEST.winRate}</div>
            <div style={S.metricSub}>{BACKTEST.trades} trades · Max DD {BACKTEST.maxDD}</div>
          </div>
        </div>
        <p style={{ fontSize: 11, color: "#334155", marginTop: 18, marginBottom: 0 }}>
          Per-agent calibration metrics pending ≥50 completed LLM-backed pipeline runs.
        </p>
      </div>
    </div>
  );
}
