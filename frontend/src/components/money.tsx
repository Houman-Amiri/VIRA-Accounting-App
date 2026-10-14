/**
 * <Money /> — the mandated money display. ISO 4217 currency code, optional
 * Persian label, inflow/outflow color coding, accounting-style negatives
 * `(-۱۲۳٬۴۵۶)`, tabular monospace digits isolated from RTL flow.
 * Accepts the API's exact 4-decimal strings and formats them losslessly.
 */
import * as React from "react";
import { Decimal, toDecimal, type MoneyLike } from "@/lib/money";
import { faNumber } from "@/lib/fa";
import { cn } from "@/lib/cn";

export interface MoneyProps {
  value: MoneyLike | null | undefined;
  /** ISO 4217 code shown after the amount (default TOMAN). */
  currency?: string;
  /** Hide the currency code. */
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
  currency = "TOMAN",
  hideCurrency = false,
  signedColors = false,
  direction = "neutral",
  accounting = true,
  className,
  title,
}: MoneyProps): React.JSX.Element {
  let amount: Decimal;
  try {
    amount = toDecimal(value);
  } catch {
    amount = new Decimal(0);
  }
  const negative = amount.isNegative();
  // Keep exactly 4 decimals trimmed of trailing zeros: "12.5000" → "12.5"
  const fixed = amount.abs().toFixed(4).replace(/(\.\d*?)0+$/, "$1").replace(/\.$/, "");
  const shown = faNumber(fixed);
  const body = accounting && negative ? `(${shown})` : negative ? `−${shown}` : shown;

  const tone =
    signedColors || direction !== "neutral"
      ? direction === "inflow" || (direction === "neutral" && signedColors && !negative && !amount.isZero())
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
      {!hideCurrency && <span className="text-[0.75em] text-muted-foreground">{currency}</span>}
    </span>
  );
}
