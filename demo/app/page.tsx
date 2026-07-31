import { readFileSync } from "fs";
import { join } from "path";
import Dashboard from "./Dashboard";

const TICKERS = ["AAPL", "MSFT", "NVDA", "TSLA", "META"];

export default function Page() {
  const runs: Record<string, TickerRun> = {};
  for (const t of TICKERS) {
    const raw = readFileSync(join(process.cwd(), "data", `${t}.json`), "utf-8");
    runs[t] = JSON.parse(raw);
  }
  return <Dashboard runs={runs} tickers={TICKERS} />;
}

export interface AgentThesis {
  agent: string;
  ticker: string;
  signal: string;
  confidence: number;
  reasoning: string;
}

export interface TickerRun {
  ticker: string;
  signal: string;
  confidence: number;
  approved: boolean;
  risk_notes: string;
  reasoning: string;
  theses: AgentThesis[];
  run_timestamp: string;
}
