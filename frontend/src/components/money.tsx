/**
 * <Money /> — the mandated money display. Exact decimal.js rendering of the
 * API's fixed 4-decimal strings (never float), ISO/unit-aware:
 *
 * - `currency="IRR"` (default) — stored Rials, displayed Tomans (÷10 applied
 *   exactly once here, per config `display_currency="IRT"`); label «تومان».
 *   `display="source"` shows raw Rials with label «ریال».
 * - `currency="TOMAN"` — value already in Tomans (e.g. price calculator),
 *   shown as-is with label «تومان».
 * - any other ISO 4217 code — shown as-is with the code label (foreign money).
 *
 * Inflow/outflow color coding, accounting negatives `(…)` and LTR-isolated
 * tabular digits throughout.
 */
import * as React from "react";
import { useTranslation } from "react-i18next";
import { Decimal, rialToToman, toDecimal, type MoneyLike } from "@/lib/money";
import { faNumber } from "@/lib/fa";
import { cn } from "@/lib/cn";

export interface MoneyProps {
  value: MoneyLike | null | undefined;
  /** Currency of the given value (ISO 4217, or "IRR"/"TOMAN"). Default IRR. */
  currency?: string;
  /** For IRR values: "toman" (÷10, default) or "source" (Rials). */
  display?: "toman" | "source";
  /** Hide the unit label. */
  hideCurrency?: boolean;
  /** Color negative amounts as outflow (red) and positive as inflow (green). */
  signedColors?: boolean;
  /** Force a direction: inflow (positive-green) / outflow (negative-red) / neutral. */
  direction?: "inflow" | "outflow" | "neutral";
  /** Show negatives as `(x)` instead of `−x`. */
  accounting?: boolean;
  className?: string;
  title?: string;
}

export function Money({
  value,
  currency = "IRR",
  display = "toman",
  hideCurrency = false,
  signedColors = false,
  direction = "neutral",
  accounting = true,
  className,
  title,
}: MoneyProps): React.JSX.Element {
  const { t } = useTranslation();
  let amount: Decimal;
  try {
    amount = toDecimal(value);
  } catch {
    amount = new Decimal(0);
  }

  let label = currency;
  if (currency === "IRR") {
    if (display === "toman") {
      amount = rialToToman(amount);
      label = t("money.toman");
    } else {
      label = t("money.rial");
    }
  } else if (currency === "TOMAN") {
    label = t("money.toman");
  }

  const negative = amount.isNegative();
  // A 4-decimal Rial can require 5 Toman decimals after ÷10; never round
  // away the smallest stored amount (e.g. a trial-balance difference).
  const fixed = amount
    .abs()
    .toFixed(currency === "IRR" && display === "toman" ? 5 : 4)
    .replace(/(\.\d*?)0+$/, "$1")
    .replace(/\.$/, "");
  const shown = faNumber(fixed);
  const body = accounting && negative ? `(${shown})` : negative ? `−${shown}` : shown;

  const tone =
    signedColors || direction !== "neutral"
      ? direction === "inflow" ||
        (direction === "neutral" && signedColors && !negative && !amount.isZero())
        ? "text-positive"
        : direction === "outflow" || (direction === "neutral" && signedColors && negative)
          ? "text-negative"
          : "text-foreground"
      : "text-foreground";

  return (
    <span
      className={cn("num inline-flex items-baseline gap-1 whitespace-nowrap", tone, className)}
      title={title}
      dir="ltr"
    >
      <span>{body}</span>
      {!hideCurrency && <span className="text-[0.75em] text-muted-foreground">{label}</span>}
    </span>
  );
}
