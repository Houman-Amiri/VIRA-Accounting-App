import { useCalendar } from "@/lib/calendar-settings";
/**
 * تطبیق بانکی — dual-pane reconciliation with live difference header and
 * confidence badges (auto ≥85%, suggestion 60–84%, manual).
 */
import * as React from "react";
import { trackEvent } from "@/lib/analytics";
import { scoreMatch, confidenceOf, CONFIDENCE_LABELS, type MatchCandidate } from "@/lib/similarity";
import { Money } from "@/components/money";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { sumMoney } from "@/lib/money";
import { faDate } from "@/lib/fa";
import { Check, Link2, X } from "lucide-react";

// Demo fixtures (server data joins in Phase 5 hardening).
const bankLines: MatchCandidate[] = [
  {
    amount: "1250000.0000",
    dateIso: "2026-10-01",
    description: "واریز به ازای فاکتور ۱۰۲۴ شرکت آریا",
    refNo: "1024",
  },
  {
    amount: "480000.0000",
    dateIso: "2026-10-03",
    description: "خرید فیلامنت PLA سفید",
    refNo: "8811",
  },
  {
    amount: "2500000.0000",
    dateIso: "2026-10-05",
    description: "فروش عمده پایه موبایل",
    refNo: "5510",
  },
];
const openTx: MatchCandidate[] = [
  {
    amount: "1250000.0000",
    dateIso: "2026-10-01",
    description: "دریافت از آریا — فاکتور ۱۰۲۴",
    refNo: "1024",
  },
  {
    amount: "480000.0000",
    dateIso: "2026-10-04",
    description: "فیلامنت PLA سفید — فروشنده پارس",
    refNo: "8811",
  },
  {
    amount: "1700000.0000",
    dateIso: "2026-10-06",
    description: "فروش عمده پایه موبایل — بازارگاه",
    refNo: "5510",
  },
];

export function ReconcilePage(): React.JSX.Element {
  const { calendar } = useCalendar();
  const [matched, setMatched] = React.useState<Record<number, number | null>>({});

  const scored = React.useMemo(
    () =>
      bankLines.map((line) => {
        const candidates = openTx.map((tx, ti) => ({ tx, ti, match: scoreMatch(line, tx) }));
        candidates.sort((a, b) => b.match.score - a.match.score);
        return { line, best: candidates[0] };
      }),
    [],
  );

  const matchedCount = Object.values(matched).filter((v) => v !== undefined && v !== null).length;
  const bankTotal = sumMoney(bankLines.map((l) => l.amount));
  const txTotal = sumMoney(openTx.map((t) => t.amount));
  const delta = bankTotal.minus(txTotal);

  return (
    <div className="space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">تطبیق بانکی</h1>
        {/* Live difference header */}
        <div className="flex items-center gap-4 rounded-lg border bg-card px-4 py-2">
          <div>
            <div className="text-xs text-muted-foreground">مغایرت زنده</div>
            <Money value={delta.toFixed(4)} signedColors accounting={false} />
          </div>
          <div>
            <div className="text-xs text-muted-foreground">تطبیق‌یافته</div>
            <span className="num">
              {matchedCount} / {bankLines.length}
            </span>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">ردیف‌های بانک</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {scored.map(({ line, best }, i) => {
              const conf = confidenceOf(best.match);
              return (
                <div
                  key={i}
                  className="rounded-lg border p-3 hover:bg-muted/40"
                  data-testid={`bank-line-${i}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="text-sm">{line.description}</span>
                    <Money value={line.amount} hideCurrency />
                  </div>
                  <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                    <span className="num">{faDate(line.dateIso, calendar)}</span>
                    <Badge
                      variant={
                        conf === "auto" ? "success" : conf === "suggested" ? "warning" : "outline"
                      }
                      data-testid={`confidence-${i}`}
                    >
                      {CONFIDENCE_LABELS[conf]} — <span className="num">{best.match.score}%</span>
                    </Badge>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">تراکنش‌های باز دفتر</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {openTx.map((tx, i) => (
              <div key={i} className="flex items-center justify-between rounded-lg border p-3">
                <div>
                  <div className="text-sm">{tx.description}</div>
                  <div className="num text-xs text-muted-foreground">
                    {faDate(tx.dateIso, calendar)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Money value={tx.amount} hideCurrency />
                  <Button size="icon" variant="ghost" aria-label="تطبیق">
                    <Link2 />
                  </Button>
                  <Button size="icon" variant="ghost" aria-label="نادیده گرفتن">
                    <X />
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Button
        className="w-full"
        data-testid="confirm-matches"
        onClick={() => {
          trackEvent("reconciliation_completed", { route: "/reconcile", status: "ok" });
          setMatched(
            Object.fromEntries(
              scored.map(({ best }, i) => [
                i,
                confidenceOf(best.match) !== "manual" ? best.ti : null,
              ]),
            ),
          );
        }}
      >
        <Check /> تأیید تطبیق‌های پیشنهادی
      </Button>
    </div>
  );
}
