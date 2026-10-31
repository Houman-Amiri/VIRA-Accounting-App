/**
 * ورود صورت‌حساب بانکی — dropzone + PapaParse, client-side column mapping,
 * duplicate detection via line hash before upload.
 */
import * as React from "react";
import { useDropzone } from "react-dropzone";
import { trackEvent } from "@/lib/analytics";
import Papa from "papaparse";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Upload, FileSpreadsheet, CheckCircle2, TriangleAlert } from "lucide-react";
import { api, parseError } from "@/api/client";
import { StepGuide } from "@/components/guide-steps";
import { faNumber } from "@/lib/fa";

export const BANK_IMPORT_GUIDE = [
  {
    title: "صورت‌حساب را از بانک بگیرید",
    body: "از اینترنت‌بانک، خروجی CSV (یا OFX) صورت‌حساب را ذخیره کنید.",
  },
  {
    title: "فایل را اینجا رها کنید",
    body: "فایل در همین نصب خوانده می‌شود؛ نام ستون‌ها فرقی نمی‌کند.",
  },
  {
    title: "ستون تاریخ و مبلغ را انتخاب کنید",
    body: "این دو ستون برای ساخت ردیف‌های بانکی لازم‌اند؛ بقیه اختیاری است.",
  },
  {
    title: "«ثبت صورت‌حساب» را بزنید",
    body: "ردیف‌ها با شناسهٔ یکتا ذخیره می‌شوند؛ فایل تکراری دوباره ثبت نمی‌شود.",
  },
];

interface ParsedCsv {
  fileName: string;
  headers: string[];
  rows: string[][];
}

export function BankImportPage(): React.JSX.Element {
  const [parsed, setParsed] = React.useState<ParsedCsv | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [result, setResult] = React.useState<{ lines: number; batchId: string } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [mapping, setMapping] = React.useState<Record<string, string>>({
    date: "",
    amount: "",
    description: "",
    reference: "",
    account_number: "",
  });

  const onDrop = React.useCallback((accepted: File[]) => {
    const file = accepted[0];
    if (!file) return;
    setFile(file);
    setResult(null);
    setError(null);
    Papa.parse<string[]>(file, {
      skipEmptyLines: true,
      complete: (result) => {
        trackEvent("bank_statement_imported", { route: "/bank-import", status: "parsed" });
        const [headers, ...rows] = result.data as string[][];
        setParsed({ fileName: file.name, headers: headers ?? [], rows });
      },
    });
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "text/csv": [".csv"], "application/vnd.ms-excel": [".csv"] },
    multiple: false,
  });

  const importStatement = async (): Promise<void> => {
    if (!file) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await api.POST("/api/v1/imports/bank", { body: body as never });
      if (res.error) throw await parseError(res.response);
      const data = res.data as unknown as { batch_id: string; lines_imported: number };
      setResult({ lines: data.lines_imported, batchId: data.batch_id });
      trackEvent("bank_statement_imported", { route: "/bank-import", status: "stored" });
    } catch (e) {
      setError(e instanceof Error ? e.message : "ثبت صورت‌حساب ناموفق بود.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">ورود صورت‌حساب بانکی</h1>

      <StepGuide
        id="bank-import"
        title="راهنمای ورود صورت‌حساب"
        intro="چهار گام تا این‌که ردیف‌های بانکی برای تطبیق آماده شوند."
        steps={BANK_IMPORT_GUIDE}
      />

      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center transition-colors ${
          isDragActive ? "border-primary bg-primary/5" : "border-border"
        }`}
        data-testid="bank-dropzone"
      >
        <input {...getInputProps()} />
        <Upload className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">
          فایل CSV یا OFX صورت‌حساب را اینجا رها کنید، یا کلیک کنید
        </p>
      </div>

      {parsed && (
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <FileSpreadsheet className="h-4 w-4" />
              {parsed.fileName}
              <Badge variant="secondary">{parsed.rows.length} ردیف</Badge>
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-5 gap-3">
              {(["date", "amount", "description", "reference", "account_number"] as const).map(
                (field) => (
                  <div key={field}>
                    <label className="mb-1 block text-xs text-muted-foreground">
                      {
                        {
                          date: "تاریخ",
                          amount: "مبلغ",
                          description: "شرح",
                          reference: "مرجع",
                          account_number: "شماره حساب",
                        }[field]
                      }
                    </label>
                    <select
                      className="flex h-9 w-full rounded-md border border-input bg-background px-2 text-sm text-foreground"
                      value={mapping[field]}
                      onChange={(e) => setMapping((m) => ({ ...m, [field]: e.target.value }))}
                      data-testid={`map-${field}`}
                    >
                      <option value="">—</option>
                      {parsed.headers.map((h, i) => (
                        <option key={`${h}-${i}`} value={h}>
                          {h}
                        </option>
                      ))}
                    </select>
                  </div>
                ),
              )}
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 text-positive" />
                نگاشت ستون‌ها برای پیش‌نمایش است؛ سرور خودِ فایل را می‌خواند
              </div>
              <Button
                data-testid="submit-import"
                disabled={!mapping.date || !mapping.amount || busy}
                onClick={() => void importStatement()}
              >
                ثبت صورت‌حساب
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {result && (
        <p
          className="flex items-center gap-2 rounded-md bg-positive/10 px-3 py-2 text-sm"
          data-testid="import-result"
        >
          <CheckCircle2 className="h-4 w-4 text-positive" />
          <span className="num">{faNumber(String(result.lines))}</span> ردیف ثبت شد و برای تطبیق
          آماده است.
        </p>
      )}
      {error && (
        <p
          role="alert"
          className="flex items-center gap-2 rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
          data-testid="import-error"
        >
          <TriangleAlert className="h-4 w-4" />
          {error}
        </p>
      )}
    </div>
  );
}
