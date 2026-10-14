/**
 * ماشین‌حساب قیمت‌گذاری — normalized model of `قیمت نهایی.xlsx`
 * (product-spec §4.3), decimal.js, live breakdown table.
 */
import * as React from "react";
import {
  BREAKDOWN_LABELS,
  computePrice,
  DEFAULT_CONSTANTS,
  type PriceConstants,
  type PriceInputs,
} from "@/lib/priceCalc";
import { Money } from "@/components/money";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

export function PriceCalcPage(): React.JSX.Element {
  const [constants, setConstants] = React.useState<PriceConstants>(DEFAULT_CONSTANTS);
  const [inputs, setInputs] = React.useState<PriceInputs>({
    weightG: "30",
    printHours: "2.5",
    quantity: "10",
    variant: "plain",
    channel: "marketplace",
  });

  const breakdown = React.useMemo(() => {
    try {
      return computePrice(inputs, constants);
    } catch {
      return null;
    }
  }, [inputs, constants]);

  const setConst = (key: keyof PriceConstants, raw: string): void =>
    setConstants((c) => ({ ...c, [key]: raw }));

  return (
    <div className="mx-auto max-w-4xl space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">ماشین‌حساب قیمت‌گذاری</h1>

      <div className="grid grid-cols-2 gap-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">ورودی‌ها</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div>
              <Label>وزن محصول (گرم)</Label>
              <Input
                className="num"
                data-testid="input-weight"
                value={String(inputs.weightG)}
                onChange={(e) => setInputs((i) => ({ ...i, weightG: e.target.value }))}
              />
            </div>
            <div>
              <Label>مدت زمان پرینت (ساعت)</Label>
              <Input
                className="num"
                data-testid="input-hours"
                value={String(inputs.printHours)}
                onChange={(e) => setInputs((i) => ({ ...i, printHours: e.target.value }))}
              />
            </div>
            <div>
              <Label>تیراژ (تعداد)</Label>
              <Input
                className="num"
                data-testid="input-qty"
                value={String(inputs.quantity)}
                onChange={(e) => setInputs((i) => ({ ...i, quantity: e.target.value }))}
              />
            </div>
            <div>
              <Label>نوع</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
                value={inputs.variant}
                onChange={(e) => setInputs((i) => ({ ...i, variant: e.target.value as PriceInputs["variant"] }))}
              >
                <option value="plain">ساده</option>
                <option value="chain">حلقه‌دار (زنجیر)</option>
              </select>
            </div>
            <div>
              <Label>کانال فروش</Label>
              <select
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
                value={inputs.channel}
                onChange={(e) => setInputs((i) => ({ ...i, channel: e.target.value as PriceInputs["channel"] }))}
              >
                <option value="direct">مستقیم</option>
                <option value="marketplace">بازارگاه</option>
              </select>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">ثابت‌ها</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(
              [
                ["filamentPerGram", "فیلامنت (هر گرم)"],
                ["electricityPerKwh", "برق (هر کیلووات)"],
                ["depreciationPerHour", "استهلاک (هر ساعت)"],
                ["profitFactor", "ضریب سود"],
                ["commissionPercent", "کمیسیون (٪)"],
                ["nylonPerUnit", "نایلون (هر عدد)"],
                ["chainPerUnit", "حلقه و زنجیر"],
                ["shipmentPerBatch", "ارسال (هر محموله)"],
                ["labelPerUnit", "لیبل (هر عدد)"],
                ["bufferPercent", "بافر ریسک (٪)"],
              ] as const
            ).map(([key, label]) => (
              <div key={key} className="grid grid-cols-2 items-center gap-2">
                <Label className="text-xs">{label}</Label>
                <Input
                  className="num h-8"
                  value={String(constants[key])}
                  onChange={(e) => setConst(key, e.target.value)}
                />
              </div>
            ))}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between">
          <CardTitle className="text-base">گزارش بهای تمام‌شده</CardTitle>
          {breakdown && (
            <Badge variant="success" data-testid="final-badge">
              قیمت نهایی: <Money value={breakdown.unitFinalPrice.toFixed(4)} />
            </Badge>
          )}
        </CardHeader>
        <CardContent>
          {breakdown ? (
            <div className="divide-y">
              {(
                [
                  "unitFilamentCost",
                  "unitEnergyCost",
                  "unitDepreciationCost",
                  "unitChainCost",
                  "unitProductionCost",
                  "batchProductionCost",
                  "unitShippingShare",
                  "unitDeliveryCost",
                  "unitSalePrice",
                  "unitCommission",
                  "merchandise",
                  "buffer",
                  "unitFinalPrice",
                  "batchTotal",
                ] as const
              ).map((key) => (
                <div key={key} className="flex items-center justify-between py-2 text-sm">
                  <span className={key === "unitFinalPrice" || key === "batchTotal" ? "font-semibold" : ""}>
                    {BREAKDOWN_LABELS[key]}
                  </span>
                  <Money value={breakdown[key].toFixed(4)} hideCurrency />
                </div>
              ))}
            </div>
          ) : (
            <p className="p-6 text-center text-destructive">ورودی نامعتبر است.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
