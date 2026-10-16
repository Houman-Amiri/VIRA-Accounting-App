import { faDateTime } from "@/lib/fa";
import { useCalendar } from "@/lib/calendar-settings";
/**
 * سیستم و عملیات — Sudo-protected System & Operations (Phase 6 §8).
 * Version/commit, schema revision, last backup, one-click encrypted snapshot,
 * restore-verification, and the «بررسی به‌روزرسانی» update check (Phase 8).
 */
import * as React from "react";
import { useTranslation } from "react-i18next";
import { fmtBytes } from "@/lib/money";
import { fetchUpdateCheck, fetchUpdateStatus, type UpdateCheck } from "@/lib/update";
import { COMPILED_BUILD_ID, isStaleUi, UI_BUILD_ID } from "@/lib/build";
import { UpdateDialog } from "@/components/update-dialog";
import { useQuery } from "@tanstack/react-query";
import { api, ApiError, getSudoToken, parseError } from "@/api/client";
import { useRequestSudo } from "@/components/sudo-dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

type SystemStatus = {
  version: string;
  commit: string;
  spa_build?: string | null;
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

export function SystemPage(): React.JSX.Element {
  const { calendar } = useCalendar();
  const { t } = useTranslation();
  const requestSudo = useRequestSudo();
  const [sudoReady, setSudoReady] = React.useState(false);
  const [actionMsg, setActionMsg] = React.useState<string | null>(null);
  const [busy, setBusy] = React.useState(false);
  const [update, setUpdate] = React.useState<UpdateCheck | null>(null);
  const [updateDialogOpen, setUpdateDialogOpen] = React.useState(false);

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

  const updateStatusQuery = useQuery({
    queryKey: ["update-status"],
    queryFn: fetchUpdateStatus,
    enabled: sudoReady,
  });

  async function runBackup() {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await api.POST("/api/v1/system/backup", {});
      if (res.error) throw await parseError(res.response);
      const data = res.data as unknown as { dir: string; size_bytes: number };
      setActionMsg(t("system.backupCreated", { size: fmtBytes(data.size_bytes) }));
      void statusQuery.refetch();
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : t("system.backupError"));
    } finally {
      setBusy(false);
    }
  }

  async function verifyBackup() {
    const last = statusQuery.data?.last_backup?.path;
    if (!last) {
      setActionMsg(t("system.noBackup"));
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
      setActionMsg(data.ok ? t("system.verifyOk") : t("system.verifyFail"));
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : t("system.verifyError"));
    } finally {
      setBusy(false);
    }
  }

  async function checkUpdates() {
    setBusy(true);
    setActionMsg(null);
    try {
      const result = await fetchUpdateCheck();
      setUpdate(result);
      if (result.update_available && !result.manual_required) {
        setUpdateDialogOpen(true); // «به‌روزرسانی جدید موجود است» dialog (§4)
      }
    } catch (e) {
      setActionMsg(e instanceof ApiError ? e.message : t("system.checkError"));
    } finally {
      setBusy(false);
    }
  }

  const s = statusQuery.data;

  return (
    <div className="mx-auto max-w-4xl space-y-4" dir="rtl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">{t("system.title")}</h1>
        <Badge variant={s ? "success" : "secondary"}>
          {s ? t("system.versionBadge", { version: s.version }) : t("common:actions.loading")}
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
              <CardTitle className="text-base">{t("system.appStatus")}</CardTitle>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-2 text-sm md:grid-cols-3">
              <div>
                {t("system.version")}: <span className="num font-mono">{s.version}</span>
              </div>
              <div>
                {t("system.commit")}: <span className="num font-mono">{s.commit}</span>
              </div>
              <div>
                {t("system.environment")}: {s.environment}
              </div>
              <div>
                {t("system.python")}: <span className="num font-mono">{s.python_version}</span>
              </div>
              <div>
                {t("system.sqlite")}: <span className="num font-mono">{s.sqlite_version}</span>
              </div>
              <div>
                {t("system.migration")}:{" "}
                <span className="num font-mono">{s.alembic_revision ?? "—"}</span>
              </div>
              <div className="col-span-2 truncate">
                {t("system.database")}: <span className="font-mono text-xs">{s.database_path}</span>
              </div>
              <div>
                {t("system.scheduler")}:{" "}
                {s.scheduler_running ? (
                  <Badge variant="success">
                    {t("system.schedulerActive", { count: s.scheduler_jobs })}
                  </Badge>
                ) : (
                  <Badge variant="secondary">{t("system.schedulerInactive")}</Badge>
                )}
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("system.backup")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div>
                {t("system.lastBackup")}:{" "}
                {s.last_backup.at ? (
                  <span className="num font-mono">
                    {faDateTime(s.last_backup.at, calendar)} ({fmtBytes(s.last_backup.size_bytes)})
                  </span>
                ) : (
                  "—"
                )}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button onClick={runBackup} disabled={busy} data-testid="system-backup">
                  {t("system.backupNow")}
                </Button>
                <Button
                  variant="outline"
                  onClick={verifyBackup}
                  disabled={busy}
                  data-testid="system-verify-backup"
                >
                  {t("system.verifyBackup")}
                </Button>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">{t("system.updates")}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3 text-sm">
              <div className="flex items-center gap-2">
                <Button onClick={checkUpdates} disabled={busy} data-testid="system-check-updates">
                  {t("system.checkUpdates")}
                </Button>
                {update && (
                  <span>
                    {update.update_available
                      ? t("system.updateAvailable", { version: update.latest })
                      : update.checked
                        ? t("system.upToDate")
                        : t("system.checkFailed", { reason: update.reason ?? "عدم دسترسی" })}
                  </span>
                )}
              </div>
              <div
                className="grid grid-cols-2 gap-x-4 gap-y-1 border-t pt-3 text-xs text-muted-foreground"
                data-testid="system-build-ids"
              >
                <span>شناسهٔ ساخت نصب (SPA)</span>
                <span className="num">{s?.spa_build || "—"}</span>
                <span>شناسهٔ ساخت بارگذاری‌شده در مرورگر</span>
                <span className="num">{UI_BUILD_ID}</span>
                <span>شناسهٔ ساخت کد کامپایل‌شده</span>
                <span className="num">{COMPILED_BUILD_ID}</span>
              </div>
              {isStaleUi(s?.spa_build) && (
                <div
                  className="rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-xs"
                  data-testid="system-stale-ui"
                >
                  نسخهٔ رابط کاربری در حافظهٔ مرورگر قدیمی است (مرورگر «{UI_BUILD_ID}» را اجرا
                  می‌کند ولی این نصب «{s?.spa_build}» است). صفحه را با{" "}
                  <span className="num">Ctrl+F5</span> تازه‌سازی کنید.
                </div>
              )}
              {updateStatusQuery.data &&
                ["committed", "rolled_back", "failed"].includes(updateStatusQuery.data.state) && (
                  <p
                    role="status"
                    data-testid="system-last-update"
                    className="rounded-md border p-3 text-sm"
                  >
                    {updateStatusQuery.data.state === "committed"
                      ? "به‌روزرسانی با موفقیت انجام و سلامت برنامه تأیید شد."
                      : updateStatusQuery.data.error_fa ||
                        "به‌روزرسانی ناموفق بود؛ گزارش را بررسی کنید."}
                  </p>
                )}
              {update?.manual_required && (
                <div
                  className="space-y-1 rounded-md border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-xs"
                  data-testid="system-manual-update"
                >
                  <p className="font-semibold">{t("system.manualInstallNeeded")}</p>
                  <p>{update.reason}</p>
                  {update.choice?.packages?.[0]?.url && (
                    <a
                      className="num text-primary hover:underline"
                      href={update.choice.packages[0].url}
                      target="_blank"
                      rel="noreferrer"
                      data-testid="system-manual-download"
                    >
                      {t("system.downloadInstaller")} (
                      {fmtBytes(update.choice.packages[0].size ?? 0)})
                    </a>
                  )}
                </div>
              )}
              {update?.update_available && update.notes_fa && (
                <p className="rounded-md border bg-muted/40 px-3 py-2">{update.notes_fa}</p>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {update && (
        <UpdateDialog
          check={update}
          open={updateDialogOpen}
          onClose={() => setUpdateDialogOpen(false)}
        />
      )}
    </div>
  );
}
