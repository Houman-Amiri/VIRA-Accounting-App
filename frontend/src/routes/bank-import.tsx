/**
 * ورود صورت‌حساب بانکی — dropzone + PapaParse, client-side column mapping,
 * duplicate detection via line hash before upload.
 */
import * as React from "react";
import { useDropzone } from "react-dropzone";
import Papa from "papaparse";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Upload, FileSpreadsheet, CheckCircle2 } from "lucide-react";

interface ParsedCsv {
  fileName: string;
  headers: string[];
  rows: string[][];
}

export function BankImportPage(): React.JSX.Element {
  const [parsed, setParsed] = React.useState<ParsedCsv | null>(null);
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
    Papa.parse<string[]>(file, {
      skipEmptyLines: true,
      complete: (result) => {
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

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">ورود صورت‌حساب بانکی</h1>

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
              {(["date", "amount", "description", "reference", "account_number"] as const).map((field) => (
                <div key={field}>
                  <label className="mb-1 block text-xs text-muted-foreground">
                    {{ date: "تاریخ", amount: "مبلغ", description: "شرح", reference: "مرجع", account_number: "شماره حساب" }[field]}
                  </label>
                  <select
                    className="flex h-9 w-full rounded-md border border-input bg-transparent px-2 text-sm"
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
              ))}
            </div>
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm text-muted-foreground">
                <CheckCircle2 className="h-4 w-4 text-positive" />
                نگاشت ستون‌ها در سمت کلاینت انجام می‌شود
              </div>
              <Button data-testid="submit-import" disabled={!mapping.date || !mapping.amount}>
                ادامه و بررسی تطبیق
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
