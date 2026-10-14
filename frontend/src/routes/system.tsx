/**
 * سیستم و عملیات — Sudo-protected System & Operations (Phase 6 §8).
 * Version/commit, schema revision, last backup, one-click encrypted snapshot,
 * restore-verification, and the «بررسی به‌روزرسانی» update check (Phase 8).
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, getSudoToken, parseError } from "@/api/client";
import { useRequestSudo } from "@/components/sudo-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

type SystemStatus = {
  version: string;
  commit: string;
  environment: string;
  python_version: string;
  sqlite_version: string;
  alembic_revision: string | null;
  database_path: string;
  receipt_dir: string;
  data_dir: string;
  scheduler_enabled: boolean;
  scheduler_running: boolean;
  scheduler_jobs: number;
  last_backup: {
    at: string | null;
    path: string | null;
    size_bytes: number | null;
    ok: boolean | null;
  };
};

type UpdateCheck = {
  current: string;
  latest: string | null;
  update_available: boolean;
  notes_fa: string | null;
  checked: boolean;
  reason: string | null;
};

function fmtBytes(n: number | null): string {
  if (n == null) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

export function SystemPage(): React.JSX.Element {
  const requestSudo = useRequestSudo();
  const [sudoReady, setSudoReady] = React.useState(false);
  const [actionMsg, setActionMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [update, setUpdate] = React.useState<UpdateCheck | null>(null);

  // The whole area is sudo-protected: step up once on entry.
  React.useEffect(() => {
    if (getSudoToken()) {
      setSudoReady(true);
      return;
    }
    requestSudo()
      .then(() => setSudoReady(true))
      .catch(() => window.history.back());
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const statusQuery = useQuery({
    queryKey: ["system-status"],
    enabled: sudoReady,
    queryFn: async () => {
      const res = await api.GET("/api/v1/system/status");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as SystemStatus;
    },
  });

  async function runBackup() {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await api.POST("/api/v1/system/backup", {});
      if (res.error) throw await parseError(res.response);
      const data = res.data as unknown as { dir: string; size_bytes: number };
      setActionMsg(`پشتیبان رمزنگاری‌شده ساخته شد (${fmtBytes(data.size_bytes)}).`);
      void statusQuery.refetch();
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : "خطا در پشتیبان‌گیری");
    } finally {
      setBusy(false);
    }
  }

  async function verifyBackup() {
    const last = statusQuery.data?.last_backup?.path;
    if (!last) {
      setActionMsg("هنوز پشتیبانی ثبت نشده است.");
      return;
    }
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await api.POST("/api/v1/system/backup/verify", {
        params: { query: { path: last } },
      });
      if (res.error) throw await parseError(res.response);
      const data = res.data as unknown as { ok: boolean; integrity_check: string };
      setActionMsg(
        data.ok
          ? "راستی‌آزمایی پشتیبان موفق بود: یکپارچگی پایگاه‌داده و تراز اسناد تأیید شد."
          : "راستی‌آزمایی ناموفق بود — جزئیات در گزارش ثبت شد.",
      );
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : "خطا در راستی‌آزمایی");
    } finally {
      setBusy(false);
    }
  }

  async function checkUpdates() {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await api.GET("/api/v1/system/check-updates");
      if (res.error) throw await parseError(res.response);
      setUpdate(res.data as unknown as UpdateCheck);
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : "خطا در بررسی به‌روزرسانی");
    } finally {
      setBusy(false);
    }
  }

  const s = statusQuery.data;

  return (
    <div className="mx-auto max-w-4xl space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">سیستم و عملیات</h1>
        <Badge variant={s ? "success" : "secondary"}>
          {s ? `نسخه ${s.version}` : "در حال بارگذاری…"}
        </Badge>
      </div>

      {actionMsg && (
        <p className="rounded-md border bg-muted/40 px-3 py-2 text-sm" role="status">
          {actionMsg}
        </p>
      )}

      {s && (
        <>
          <Card>
            <CardHeader>
              <CardTitle className="text-base">وضعیت برنامه</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2 text-sm md:grid-cols-3">
              <div>
                نسخه: <span className="num font-mono">{s.version}</span>
              </div>
              <div>
                کامیت: <span className="num font-mono">{s.commit}</span>
              </div>
              <div>محیط: {s.environment}</div>
              <div>
                Python: <span className="num font-mono">{s.python_version}</span>
              </div>
              <div>
                SQLite: <span className="num font-mono">{s.sqlite_version}</span>
              </div>
              <div>
                مهاجرت دیتابیس:{" "}
                <span className="num font-mono">{s.alembic_revision ?? "—"}</span>
              </div>
              <div className="col-span-2 truncate">
                پایگاه‌داده: <span className="font-mono text-xs">{s.database_path}</span>
              </div>
              <div>
                زمان‌بند:{" "}
                {s.scheduler_running ? (
                  <Badge variant="success">فعال ({s.scheduler_jobs} کار)</Badge>
                ) : (
                  <Badge variant="secondary">غیرفعال</Badge>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">پشتیبان‌گیری</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                آخرین پشتیبان:{" "}
                {s.last_backup.at ? (
                  <span className="num font-mono">
                    {s.last_backup.at} ({fmtBytes(s.last_backup.size_bytes)})
                  </span>
                ) : (
                  "—"
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={runBackup} disabled={busy} data-testid="system-backup">
                  پشتیبان رمزنگاری‌شده اکنون
                </Button>
                <Button
                  variant="outline"
                  onClick={verifyBackup}
                  disabled={busy}
                  data-testid="system-verify-backup"
                >
                  راستی‌آزمایی پشتیبان
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">به‌روزرسانی‌ها</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center gap-2">
                <Button onClick={checkUpdates} disabled={busy} data-testid="system-check-updates">
                  بررسی به‌روزرسانی
                </Button>
                {update && (
                  <span>
                    {update.update_available
                      ? `نسخه جدید ${update.latest} موجود است.`
                      : update.checked
                        ? "شما از آخرین نسخه استفاده می‌کنید."
                        : `بررسی ممکن نشد (${update.reason ?? "عدم دسترسی"}).`}
                  </span>
                )}
              </div>
              {update?.update_available && update.notes_fa && (
                <p className="rounded-md border bg-muted/40 px-3 py-2">{update.notes_fa}</p>
              )}
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}
