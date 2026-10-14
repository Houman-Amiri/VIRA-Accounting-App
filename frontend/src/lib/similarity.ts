/**
 * Bank-reconciliation matching heuristics (deterministic, weights sum to 1).
 * Confidence ≥ 85% = auto-match candidate; 60–84% = suggestion; below = manual.
 */
import Decimal from "decimal.js";
import { toDecimal, type MoneyLike } from "./money";

export interface MatchCandidate {
  amount: MoneyLike;
  dateIso: string;
  description: string;
  refNo?: string | null;
}

export interface MatchScore {
  score: number; // 0..100
  amountMatch: boolean;
  dateDeltaDays: number | null;
  descriptionScore: number;
  refMatch: boolean;
}

const WEIGHTS = { amount: 0.45, date: 0.25, description: 0.2, ref: 0.1 } as const;

export const AUTO_MATCH_THRESHOLD = 85;
export const SUGGEST_THRESHOLD = 60;

/** Longest-common-subsequence ratio in [0,1]. */
export function lcsRatio(a: string, b: string): number {
  const s = a.trim().toLowerCase();
  const t = b.trim().toLowerCase();
  if (!s.length && !t.length) return 1;
  if (!s.length || !t.length) return 0;
  const m = s.length;
  const n = t.length;
  let prev = new Array<number>(n + 1).fill(0);
  let cur = new Array<number>(n + 1).fill(0);
  for (let i = 1; i <= m; i++) {
    for (let j = 1; j <= n; j++) {
      cur[j] = s[i - 1] === t[j - 1] ? prev[j - 1] + 1 : Math.max(prev[j], cur[j - 1]);
    }
    [prev, cur] = [cur, prev];
  }
  return prev[n] / Math.max(m, n);
}

function daysBetween(isoA: string, isoB: string): number | null {
  const a = new Date(isoA);
  const b = new Date(isoB);
  if (Number.isNaN(a.getTime()) || Number.isNaN(b.getTime())) return null;
  return Math.abs(Math.round((a.getTime() - b.getTime()) / 86_400_000));
}

/** Score how well a bank line matches an open transaction. */
export function scoreMatch(line: MatchCandidate, tx: MatchCandidate): MatchScore {
  const amountMatch = toDecimal(line.amount).equals(toDecimal(tx.amount));
  const dateDeltaDays = daysBetween(line.dateIso, tx.dateIso);
  const descriptionScore = lcsRatio(line.description, tx.description);
  const refMatch = Boolean(line.refNo && tx.refNo && line.refNo === tx.refNo);

  const dateScore = dateDeltaDays === null ? 0 : Math.max(0, 1 - dateDeltaDays / 30);
  const score =
    (amountMatch ? WEIGHTS.amount : 0) +
    dateScore * WEIGHTS.date +
    descriptionScore * WEIGHTS.description +
    (refMatch ? WEIGHTS.ref : 0);

  return {
    score: Math.round(score * 1000) / 10,
    amountMatch,
    dateDeltaDays,
    descriptionScore: Math.round(descriptionScore * 100) / 100,
    refMatch,
  };
}

export type Confidence = "auto" | "suggested" | "manual";

export function confidenceOf(score: MatchScore): Confidence {
  if (score.score >= AUTO_MATCH_THRESHOLD && score.amountMatch) return "auto";
  if (score.score >= SUGGEST_THRESHOLD) return "suggested";
  return "manual";
}

export const CONFIDENCE_LABELS: Record<Confidence, string> = {
  auto: "تطبیق خودکار",
  suggested: "پیشنهاد",
  manual: "دستی",
};

/** Best candidate for a line, or null when nothing reaches the suggest floor. */
export function bestMatch(
  line: MatchCandidate,
  txs: MatchCandidate[],
): { tx: MatchCandidate; match: MatchScore } | null {
  let best: { tx: MatchCandidate; match: MatchScore } | null = null;
  for (const tx of txs) {
    const match = scoreMatch(line, tx);
    if (!best || match.score > best.match.score) best = { tx, match };
  }
  return best && best.match.score >= SUGGEST_THRESHOLD ? best : null;
}

export { Decimal, toDecimal };
