/**
 * رسیدها — receipt upload (dropzone → POST /documents/receipts), OCR status
 * badge, PDF/image viewer scaffold (react-pdf + react-zoom-pan-pinch).
 */
import * as React from "react";
import { useDropzone } from "react-dropzone";
import { api, parseError } from "@/api/client";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { FileUp, ScanText } from "lucide-react";

interface ReceiptMeta {
  id: string;
  filename: string;
  ocr_status: string;
}

export function ReceiptsPage(): React.JSX.Element {
  const [receipts, setReceipts] = React.useState<ReceiptMeta[]>([]);
  const [error, setError] = React.useState<string | null>(null);

  const onDrop = React.useCallback(async (accepted: File[]) => {
    const file = accepted[0];
    if (!file) return;
    setError(null);
    try {
      const body = new FormData();
      body.append("file", file);
      const res = await api.POST("/api/v1/documents/receipts", { body: body as never });
      if (res.error) throw await parseError(res.response);
      const created = res.data as unknown as ReceiptMeta;
      setReceipts((prev) => [created, ...prev]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "خطا در آپلود رسید");
    }
  }, []);

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: { "application/pdf": [".pdf"], "image/*": [".png", ".jpg", ".jpeg", ".webp"] },
    multiple: true,
  });

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">اسناد و رسیدها</h1>

      <div
        {...getRootProps()}
        className={`flex cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-10 text-center ${
          isDragActive ? "border-primary bg-primary/5" : "border-border"
        }`}
      >
        <input {...getInputProps()} />
        <FileUp className="mb-2 h-8 w-8 text-muted-foreground" />
        <p className="text-sm text-muted-foreground">برای استخراج خودکار اطلاعات، تصویر رسید یا PDF را اینجا رها کنید</p>
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">رسیدهای اخیر</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {receipts.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-lg border p-3">
              <div className="flex items-center gap-2">
                <ScanText className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm">{r.filename}</span>
              </div>
              <Badge
                variant={
                  r.ocr_status === "done" ? "success" : r.ocr_status === "failed" ? "destructive" : "secondary"
                }
              >
                {r.ocr_status === "done" ? "OCR کامل" : r.ocr_status === "failed" ? "OCR ناموفق" : "در صف OCR"}
              </Badge>
            </div>
          ))}
          {receipts.length === 0 && (
            <p className="p-6 text-center text-sm text-muted-foreground">هنوز رسیدی ثبت نشده است.</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
