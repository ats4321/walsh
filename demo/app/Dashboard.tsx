"use client";

import React, { useState } from "react";
import type { TickerRun, AgentThesis } from "./page";

// ─── Constants ───────────────────────────────────────────────────────────────

const AGENT_LABEL: Record<string, string> = {
  fundamental: "Fundamental",
  technical: "Technical",
  sentiment: "Sentiment",
  macro: "Macro",
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

// Linear interpolate t ∈ [0,1] clamped, 0 = conf 50%, 1 = conf 80%+
function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * Math.max(0, Math.min(1, t));
}
function cT(confidence: number): number {
  return (confidence - 0.5) / 0.3;
}

// Confidence tiers: <60% muted, 60-75% standard, 75%+ saturated
function signalColor(signal: string, confidence: number): string {
  const up = signal === "STRONG_BUY" || signal === "BUY";
  const dn = signal === "STRONG_SELL" || signal === "SELL";
  if (!up && !dn) return "#64748b";
  if (up) {
    if (confidence >= 0.75) return "#16a34a";
    if (confidence >= 0.60) return "#22c55e";
    return "#4ade80";
  }
  if (confidence >= 0.75) return "#dc2626";
  if (confidence >= 0.60) return "#ef4444";
  return "#fca5a5";
}

// Signal font size scales with conviction — continuous, not stepped
function signalFontSize(confidence: number): number {
  return Math.round(lerp(13, 21, cT(confidence)));
}

// Convert 0-1 alpha to two-digit hex for embedding in color strings
function ax(alpha: number): string {
  return Math.round(Math.max(0, Math.min(1, alpha)) * 255).toString(16).padStart(2, "0");
}

// Box-shadow encodes both elevation AND confidence — ring alpha and glow both interpolate.
function agentCardShadow(signal: string, confidence: number, hovered: boolean): string {
  const color = signalColor(signal, confidence);
  const neutral = signal === "HOLD" || signal === "UNKNOWN";
  const t = cT(confidence);
  const ringAlpha = neutral ? 0.07 : lerp(0.08, 0.44, t);
  // Glow starts fading in above 65% confidence
  const glowOpacity = neutral ? 0 : lerp(0, 0.14, Math.max(0, (confidence - 0.65) / 0.15));
  const glow = glowOpacity > 0.005 ? `, 0 0 20px ${color}${ax(glowOpacity)}` : "";
  return hovered
    ? `0 0 0 1.5px ${color}${ax(Math.min(ringAlpha * 1.6, 0.7))}, 0 14px 32px rgba(0,0,0,0.65)${glow}`
    : `0 0 0 1px ${color}${ax(ringAlpha)}, 0 4px 12px rgba(0,0,0,0.55), 0 1px 3px rgba(0,0,0,0.35)${glow}`;
}

// ─── Design tokens ────────────────────────────────────────────────────────────
// Type scale: 11 (label) · 13 (body) · 15 (body-lg) · 20 (value) · 28 (hero)
// Spacing: 4 · 8 · 12 · 16 · 24 · 32 · 48

const T = {
  label:   { fontSize: 11, fontWeight: 600, textTransform: "uppercase" as const, letterSpacing: "1.2px", color: "#475569" },
  body:    { fontSize: 13, fontWeight: 400, lineHeight: 1.6, color: "#94a3b8" },
  bodyLg:  { fontSize: 15, fontWeight: 400, lineHeight: 1.65, color: "#94a3b8" },
  value:   { fontSize: 20, fontWeight: 700, letterSpacing: "-0.3px", color: "#f1f5f9" },
  hero:    { fontSize: 28, fontWeight: 800, letterSpacing: "-0.8px", color: "#f1f5f9" },
};

// Card-style box — elevation via layered shadow instead of flat border
const cardStyle = {
  background: "#111118",
  borderRadius: 12,
  boxShadow: "0 0 0 1px rgba(255,255,255,0.06), 0 2px 8px rgba(0,0,0,0.45), 0 1px 2px rgba(0,0,0,0.3)",
};

// ─── Static chart data ────────────────────────────────────────────────────────

// ponytail: hardcoded from actual backtest output; regenerate with backtest/engine.py if data changes
const EQUITY_WALSH = [100.0, 104.5, 108.2, 113.5, 117.8, 122.0, 126.4, 132.1, 138.5, 131.2, 126.8, 155.2, 175.5];
const EQUITY_BNH   = [100.0, 113.0, 122.0, 146.6, 152.9, 181.5, 197.6, 201.2, 208.1, 187.7, 190.7, 216.7, 219.8];
const EQUITY_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

const BACKTEST = {
  walshReturn: "+75.52%",
  bnahReturn: "+119.75%",
  sharpe: "2.36",
  bnahSharpe: "2.86",
  maxDD: "−13.50%",
  winRate: "76.2%",
  trades: "21",
  period: "Jan – Dec 2023 · AAPL · MSFT · NVDA",
};

// ─── Components ───────────────────────────────────────────────────────────────

function EquityCurve() {
  const VW = 560, VH = 180, PL = 40, PR = 16, PT = 12, PB = 32;
  const cw = VW - PL - PR, ch = VH - PT - PB;
  const n = EQUITY_WALSH.length;
  const yMin = 88, yMax = 232, yRange = yMax - yMin;

  const px = (i: number) => PL + (i / (n - 1)) * cw;
  const py = (v: number) => PT + (1 - (v - yMin) / yRange) * ch;
  const pts = (arr: number[]) => arr.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`).join(" ");

  const gapPolygon = [
    ...EQUITY_BNH.map((v, i) => `${px(i).toFixed(1)},${py(v).toFixed(1)}`),
    ...[...EQUITY_WALSH].reverse().map((v, i) => `${px(n - 1 - i).toFixed(1)},${py(v).toFixed(1)}`),
  ].join(" ");

  // Show every other month label to avoid crowding
  const labelIdxs = [0, 2, 4, 6, 8, 10, 11];

  return (
    <div>
      <svg viewBox={`0 0 ${VW} ${VH}`} style={{ display: "block", width: "100%", height: "auto", overflow: "visible" }}>
        {[100, 140, 180, 220].map(v => (
          <line key={v} x1={PL} x2={VW - PR} y1={py(v).toFixed(1)} y2={py(v).toFixed(1)}
            stroke="rgba(255,255,255,0.05)" strokeWidth={1} />
        ))}
        {[100, 150, 200].map(v => (
          <text key={v} x={PL - 6} y={(py(v) + 4).toFixed(1)}
            textAnchor="end" fontSize={10} fill="#334155">{v}%</text>
        ))}
        {labelIdxs.map(i => (
          <text key={i} x={px(i).toFixed(1)} y={VH - 8}
            textAnchor="middle" fontSize={10} fill="#334155">{EQUITY_LABELS[i]}</text>
        ))}
        <polygon points={gapPolygon} fill="rgba(239,68,68,0.08)" />
        <polyline points={pts(EQUITY_BNH)} fill="none" stroke="#334155" strokeWidth={1.5} strokeDasharray="4 3" />
        <polyline points={pts(EQUITY_WALSH)} fill="none" stroke="#6366f1" strokeWidth={2} />
        <circle cx={px(n - 1).toFixed(1)} cy={py(EQUITY_WALSH[n - 1]).toFixed(1)} r={3} fill="#6366f1" />
        <circle cx={px(n - 1).toFixed(1)} cy={py(EQUITY_BNH[n - 1]).toFixed(1)} r={3} fill="#334155" />
      </svg>
      <div style={{ display: "flex", gap: 16, justifyContent: "center", marginTop: 10, flexWrap: "wrap" }}>
        {[
          { stroke: "#6366f1", dash: undefined, label: "Walsh (+75.5%)" },
          { stroke: "#334155", dash: "4 3",     label: "B&H (+119.8%)" },
        ].map(({ stroke, dash, label }) => (
          <span key={label} style={{ display: "flex", alignItems: "center", gap: 6, ...T.body, fontSize: 11 }}>
            <svg width={20} height={8} style={{ display: "block", flexShrink: 0 }}>
              <line x1={0} y1={4} x2={20} y2={4} stroke={stroke} strokeWidth={1.8} strokeDasharray={dash} />
            </svg>
            {label}
          </span>
        ))}
        <span style={{ display: "flex", alignItems: "center", gap: 6, ...T.body, fontSize: 11 }}>
          <svg width={14} height={8} style={{ display: "block", flexShrink: 0 }}>
            <rect width={14} height={8} rx={2} fill="rgba(239,68,68,0.20)" />
          </svg>
          Gap (−44 pp)
        </span>
      </div>
    </div>
  );
}

function ConfBar({ value, color }: { value: number; color: string }) {
  return (
    <div style={{ height: 4, borderRadius: 2, background: "rgba(255,255,255,0.06)", marginTop: 6 }}>
      <div style={{ height: "100%", width: `${Math.round(value * 100)}%`, borderRadius: 2, background: color, opacity: 0.8 }} />
    </div>
  );
}

function AgentCard({ thesis }: { thesis: AgentThesis }) {
  const [hovered, setHovered] = useState(false);
  const color = signalColor(thesis.signal, thesis.confidence);
  const conf = thesis.confidence;
  const confPct = Math.round(conf * 100);
  // Border thickness + opacity interpolate continuously 50% → 80%
  const t = cT(conf);
  const borderW = lerp(0.75, 2.5, t).toFixed(2);
  const borderAlpha = lerp(0.16, 0.90, t);
  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        ...cardStyle,
        padding: "16px",
        borderTop: `${borderW}px solid ${color}${ax(borderAlpha)}`,
        transform: hovered ? "translateY(-2px)" : "translateY(0)",
        boxShadow: agentCardShadow(thesis.signal, conf, hovered),
        transition: "transform 0.14s ease, box-shadow 0.14s ease",
      }}
    >
      {/* Agent label row */}
      <div style={{ display: "flex", alignItems: "center", gap: 5, marginBottom: 10 }}>
        <span style={{ fontSize: 13 }}>{AGENT_ICON[thesis.agent] ?? "🤖"}</span>
        <span style={{ ...T.label, letterSpacing: "0.5px", textTransform: "none", fontSize: 11 }}>
          {AGENT_LABEL[thesis.agent] ?? thesis.agent}
        </span>
      </div>

      {/* Signal — font size scales with confidence */}
      <div style={{
        fontSize: signalFontSize(thesis.confidence),
        fontWeight: 800,
        letterSpacing: "-0.3px",
        color,
        marginBottom: 6,
        lineHeight: 1,
      }}>
        {thesis.signal.replace("_", " ")}
      </div>

      {/* Confidence — weight mirrors conviction */}
      <div style={{
        ...T.body,
        fontSize: 12,
        fontWeight: conf >= 0.72 ? 600 : 400,
        color: conf >= 0.72 ? "#94a3b8" : "#475569",
        marginBottom: 4,
      }}>
        {confPct}% confidence
      </div>
      <ConfBar value={thesis.confidence} color={color} />

      <div style={{ ...T.body, fontSize: 11.5, marginTop: 10, color: "#475569" }}>{thesis.reasoning}</div>
    </div>
  );
}

function LimitationsBanner() {
  const [open, setOpen] = useState(false);
  return (
    <div style={{
      background: "rgba(234,179,8,0.05)",
      border: "1px solid rgba(234,179,8,0.18)",
      borderRadius: 8,
      marginBottom: 32,
      overflow: "hidden",
    }}>
      <button
        onClick={() => setOpen(o => !o)}
        style={{
          display: "flex", alignItems: "center", gap: 8, width: "100%",
          background: "none", border: "none", cursor: "pointer",
          color: "#92400e", fontSize: 12, fontWeight: 600,
          padding: "10px 14px", textAlign: "left",
          letterSpacing: "0.2px",
        }}
      >
        <span style={{ fontSize: 13 }}>⚠️</span>
        <span style={{ flex: 1 }}>Known limitation: underperforms buy-and-hold by ~44 pp</span>
        <span style={{
          fontSize: 10, fontWeight: 600, letterSpacing: "0.5px", textTransform: "uppercase",
          color: "#78350f", background: "rgba(234,179,8,0.1)", borderRadius: 3,
          padding: "2px 6px",
        }}>
          {open ? "Hide" : "Details"}
        </span>
      </button>
      <div style={{
        maxHeight: open ? "220px" : "0",
        overflow: "hidden",
        transition: "max-height 0.22s ease",
      }}>
        <div style={{ padding: "0 14px 12px", ...T.body, fontSize: 12, color: "#78350f", lineHeight: 1.65, borderTop: "1px solid rgba(234,179,8,0.12)" }}>
          The Jan–Dec 2023 backtest returned +75.5% vs +119.8% passive buy-and-hold on AAPL/MSFT/NVDA,
          underperforming by ~44 pp. The primary cause is that the volatility damper (vol_cap=40%) zeroed
          out NVDA allocation — the period's biggest winner — while the mean-reversion agent added
          conflicting SELL signals in a one-directional trend year. The immediate next step is replacing the
          hard vol_cap=40% binary cutoff in RiskManager.adjust() with continuous position-size scaling.
        </div>
      </div>
    </div>
  );
}

// Sticky header bar — shows the most important info without scrolling
function HeaderBar({ ticker, run }: { ticker: string; run: TickerRun }) {
  const color = signalColor(run.signal, run.confidence);
  const reason = (!run.approved ? run.risk_notes : run.reasoning).split(".")[0];
  return (
    <div style={{
      position: "sticky", top: 0, zIndex: 50,
      background: "rgba(9,9,14,0.88)",
      backdropFilter: "blur(14px)",
      WebkitBackdropFilter: "blur(14px)",
      borderBottom: "1px solid rgba(255,255,255,0.06)",
      padding: "0 24px",
      display: "flex", alignItems: "center", gap: 12, height: 46,
    }}>
      <span style={{ fontSize: 13, fontWeight: 700, color: "#f1f5f9", letterSpacing: "-0.2px", marginRight: 4 }}>Walsh</span>
      <span style={{ color: "#1e293b", fontSize: 16, lineHeight: 1 }}>|</span>
      <span style={{ fontSize: 13, fontWeight: 700, color: "#94a3b8" }}>{ticker}</span>
      {/* Signal badge */}
      <span style={{
        fontSize: 11, fontWeight: 700, letterSpacing: "0.4px",
        color, background: `${color}18`, border: `1px solid ${color}35`,
        borderRadius: 5, padding: "2px 8px",
      }}>
        {run.signal.replace("_", " ")}
      </span>
      {/* Approved / Vetoed */}
      <span style={{
        fontSize: 11, fontWeight: 600,
        color: run.approved ? "#22c55e" : "#ef4444",
        background: run.approved ? "rgba(34,197,94,0.10)" : "rgba(239,68,68,0.10)",
        border: `1px solid ${run.approved ? "rgba(34,197,94,0.2)" : "rgba(239,68,68,0.2)"}`,
        borderRadius: 5, padding: "2px 8px",
      }}>
        {run.approved ? "✓ Approved" : "✕ Vetoed"}
      </span>
      {/* Reason — truncated, hidden on narrow screens via CSS class */}
      <span className="header-reason" style={{ ...T.body, fontSize: 11, color: "#334155", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
        {reason}
      </span>
    </div>
  );
}

// ─── Main dashboard ────────────────────────────────────────────────────────────

export default function Dashboard({ runs, tickers }: { runs: Record<string, TickerRun>; tickers: string[] }) {
  const [ticker, setTicker] = useState(tickers[0]);
  const run = runs[ticker];
  const finalColor = signalColor(run.signal, run.confidence);

  return (
    <>
      {/* Responsive styles + hover that can't be expressed in inline style */}
      <style>{`
        /* Clip our own content. Note: viewport-fixed overlays (e.g. Vercel toolbar) are
           positioned relative to the viewport and cannot be clipped by overflow rules here. */
        html { overflow-x: hidden; }
        body { overflow-x: hidden; position: relative; }
        .analyst-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; }
        .synthesis-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
        .header-reason { display: block; min-width: 0; }
        @media (max-width: 800px) {
          .analyst-grid { grid-template-columns: repeat(2, 1fr); }
          .synthesis-grid { grid-template-columns: 1fr; }
        }
        @media (max-width: 520px) {
          .analyst-grid { grid-template-columns: 1fr; }
          .header-reason { display: none; }
        }
        select:focus { outline: 2px solid rgba(99,102,241,0.5); outline-offset: 2px; }
        select option { background: #1a1a22; }
      `}</style>

      <HeaderBar ticker={ticker} run={run} />

      <div style={{ maxWidth: 1040, margin: "0 auto", padding: "40px 24px 64px", position: "relative", isolation: "isolate" } as React.CSSProperties}>

        {/* Page title */}
        <div style={{ marginBottom: 32 }}>
          <h1 style={{ fontSize: 22, fontWeight: 800, margin: 0, letterSpacing: "-0.5px", color: "#f1f5f9" }}>
            Walsh Demo
          </h1>
          <p style={{ ...T.body, marginTop: 6, marginBottom: 0, fontSize: 12 }}>
            Multi-agent stock research pipeline · Pre-generated runs (no live API calls)
          </p>
        </div>

        <LimitationsBanner />

        {/* Ticker select */}
        <div style={{ position: "relative", display: "inline-block", marginBottom: 36 }}>
          <select
            value={ticker}
            onChange={(e) => setTicker(e.target.value)}
            style={{
              appearance: "none",
              background: "#111118",
              border: "1px solid rgba(255,255,255,0.09)",
              boxShadow: "0 1px 3px rgba(0,0,0,0.4)",
              color: "#e2e8f0",
              padding: "9px 38px 9px 14px",
              borderRadius: 8,
              fontSize: 13,
              cursor: "pointer",
              outline: "none",
              width: 280,
            }}
          >
            {tickers.map((t) => (
              <option key={t} value={t}>{TICKER_LABEL[t] ?? t}</option>
            ))}
          </select>
          <svg width={12} height={12} viewBox="0 0 12 12" fill="none"
            style={{ position: "absolute", right: 12, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }}>
            <path d="M2 4l4 4 4-4" stroke="#475569" strokeWidth={1.5} strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>

        {/* ── Analyst signals ─────────────────────────────────────────────── */}
        <section style={{ marginBottom: 40 }}>
          <div style={{ ...T.label, marginBottom: 14 }}>Analyst Signals</div>
          <div className="analyst-grid">
            {run.theses.map((t) => <AgentCard key={t.agent} thesis={t} />)}
          </div>
        </section>

        {/* ── Portfolio Manager + Risk Manager (side by side) ──────────────── */}
        <section style={{ marginBottom: 40 }}>
          <div style={{ ...T.label, marginBottom: 14 }}>Decision</div>
          <div className="synthesis-grid">

            {/* Portfolio Manager */}
            <div style={{ ...cardStyle, padding: "20px 22px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
                <span style={{ fontSize: 15 }}>🧠</span>
                <span style={{ ...T.label, fontSize: 10 }}>Portfolio Manager Synthesis</span>
              </div>
              <p style={{ ...T.body, margin: 0, fontSize: 13 }}>{run.reasoning}</p>
            </div>

            {/* Risk Manager */}
            <div style={{ ...cardStyle, padding: "20px 22px" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 7, marginBottom: 14 }}>
                <span style={{ fontSize: 15 }}>🛡️</span>
                <span style={{ ...T.label, fontSize: 10 }}>Risk Manager Decision</span>
              </div>
              {/* Verdict pill */}
              <div style={{
                display: "inline-flex", alignItems: "center", gap: 8,
                padding: "5px 12px", borderRadius: 20, marginBottom: 12,
                fontSize: 12, fontWeight: 700, letterSpacing: "0.2px",
                background: run.approved ? "rgba(34,197,94,0.1)" : "rgba(239,68,68,0.1)",
                color: run.approved ? "#22c55e" : "#ef4444",
                border: `1px solid ${run.approved ? "rgba(34,197,94,0.22)" : "rgba(239,68,68,0.22)"}`,
              }}>
                {run.approved ? "✓ APPROVED" : "✕ VETOED"}
                <span style={{ color: "#475569", fontWeight: 400 }}>·</span>
                <span>Final: </span>
                <span style={{ color: finalColor }}>{run.signal.replace("_", " ")}</span>
              </div>
              <p style={{ ...T.body, margin: 0, fontSize: 13 }}>{run.risk_notes}</p>
            </div>

          </div>
        </section>

        {/* ── Backtest Results ─────────────────────────────────────────────── */}
        <section>
          <div style={{ ...T.label, marginBottom: 14 }}>
            📉 Backtest Results
            <span style={{
              display: "inline-block", marginLeft: 10, fontSize: 9, fontWeight: 700,
              letterSpacing: "0.8px", textTransform: "uppercase",
              background: "rgba(34,197,94,0.10)", color: "#16a34a",
              border: "1px solid rgba(34,197,94,0.2)",
              padding: "2px 6px", borderRadius: 3,
            }}>Real Data</span>
          </div>
          <div style={{ ...cardStyle, padding: "24px" }}>

            <p style={{ ...T.body, fontSize: 11, margin: "0 0 4px" }}>
              Fixed universe: AAPL · MSFT · NVDA — numbers do not change with ticker selection above.
            </p>
            <p style={{ ...T.body, fontSize: 11, margin: "0 0 20px" }}>
              {BACKTEST.period} · <strong style={{ color: "#475569", fontWeight: 600 }}>Rule-based approximation</strong> —
              deterministic SMA/momentum agents, not the LLM-powered agents above.
            </p>

            {/* ── Stats row ABOVE chart ── */}
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, marginBottom: 24 }}>

              <div style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "14px 16px", border: "1px solid rgba(255,255,255,0.05)", boxShadow: "0 2px 10px rgba(0,0,0,0.45), 0 1px 3px rgba(0,0,0,0.3)" }}>
                <div style={T.label}>Sharpe Ratio</div>
                <div style={{ ...T.hero, marginTop: 8 }}>{BACKTEST.sharpe}</div>
                <div style={{ ...T.body, fontSize: 11, marginTop: 4 }}>
                  vs {BACKTEST.bnahSharpe} B&amp;H{" "}
                  <span style={{ color: "#f87171", fontWeight: 700 }}>−0.5</span>
                </div>
              </div>

              <div style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "14px 16px", border: "1px solid rgba(255,255,255,0.05)", boxShadow: "0 2px 10px rgba(0,0,0,0.45), 0 1px 3px rgba(0,0,0,0.3)" }}>
                <div style={T.label}>Total Return</div>
                {/* Positive value stays neutral — the red delta badge communicates underperformance */}
                <div style={{ ...T.hero, marginTop: 8 }}>{BACKTEST.walshReturn}</div>
                <div style={{ ...T.body, fontSize: 11, marginTop: 4 }}>
                  vs {BACKTEST.bnahReturn} B&amp;H{" "}
                  <span style={{ color: "#f87171", fontWeight: 700 }}>−44.2 pp</span>
                </div>
              </div>

              <div style={{ background: "rgba(255,255,255,0.03)", borderRadius: 8, padding: "14px 16px", border: "1px solid rgba(255,255,255,0.05)", boxShadow: "0 2px 10px rgba(0,0,0,0.45), 0 1px 3px rgba(0,0,0,0.3)" }}>
                <div style={T.label}>Win Rate</div>
                <div style={{ ...T.hero, marginTop: 8, color: "#22c55e" }}>{BACKTEST.winRate}</div>
                <div style={{ ...T.body, fontSize: 11, marginTop: 4 }}>
                  {BACKTEST.trades} trades · Max DD {BACKTEST.maxDD}
                </div>
              </div>

            </div>

            {/* Chart */}
            <EquityCurve />
            <p style={{ ...T.body, fontSize: 10, textAlign: "center", margin: "8px 0 0", color: "#334155" }}>
              Portfolio value (% of initial $100k) · monthly snapshots
            </p>

            <p style={{ ...T.body, fontSize: 11, marginTop: 16, marginBottom: 0, color: "#334155" }}>
              Per-agent calibration metrics pending ≥50 completed LLM-backed pipeline runs.
            </p>
          </div>
        </section>

      </div>
    </>
  );
}
