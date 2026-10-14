/**
 * <UpdateDialog /> — the mandated Phase 8 §4 RTL Persian update dialog.
 *
 * Title «به‌روزرسانی جدید موجود است», message
 * «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z). آیا می‌خواهید دانلود و نصب شود؟»
 * with «دانلود و نصب» / «بعداً» / «مشاهدهٔ جزئیات», download progress with the
 * delta size, verification status, and a "restart to finish" step. Failures
 * show «خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.» with the log path.
 */
import * as React from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { fmtBytes } from "@/lib/money";
import { useUpdateFlow, type UpdateCheck } from "@/lib/update";

export interface UpdateDialogProps {
  check: UpdateCheck;
  open: boolean;
  onClose: () => void;
}

type Phase = "confirm" | "downloading" | "verifying" | "staged" | "applying" | "done" | "failed";

export function UpdateDialog({
  check,
  open,
  onClose,
}: UpdateDialogProps): React.JSX.Element | null {
  const { t } = useTranslation();
  const { download, apply, status } = useUpdateFlow();
  const [phase, setPhase] = React.useState<Phase>("confirm");
  const [showDetails, setShowDetails] = React.useState(false);

  React.useEffect(() => {
    const s = status.data;
    if (!s) return;
    if (s.state === "downloading") setPhase("downloading");
    else if (s.state === "verifying") setPhase("verifying");
    else if (s.state === "staged") setPhase("staged");
    else if (s.state === "applying") setPhase("applying");
    else if (s.state === "failed") setPhase("failed");
    else if (s.state === "committed") setPhase("done");
  }, [status.data]);

  if (!open) return null;

  const total = check.choice?.total_bytes ?? 0;
  const isDelta = (check.choice?.kind ?? "full") !== "full";
  const done = status.data?.downloaded_bytes ?? 0;
  const pct = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
  const errorFa = status.data?.error_fa ?? null;
  const logPath = status.data?.log_path ?? "";

  const start = (): void => {
    setPhase("downloading");
    download.mutate(undefined, {
      onError: () => setPhase("failed"),
    });
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      role="presentation"
      data-testid="update-dialog-overlay"
    >
      <div
        dir="rtl"
        role="dialog"
        aria-modal="true"
        aria-label={t("update.title")}
        className="w-full max-w-md space-y-4 rounded-xl border bg-card p-5 shadow-2xl"
        data-testid="update-dialog"
      >
        <h2 className="text-lg font-bold">{t("update.title")}</h2>

        {phase === "confirm" && (
          <>
            <p className="text-sm" data-testid="update-message">
              {t("update.message", { version: check.latest })}
            </p>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded-md border px-2 py-0.5" data-testid="update-package-kind">
                {isDelta ? t("update.deltaBadge") : t("update.fullBadge")}
              </span>
              <span className="num" data-testid="update-package-size">
                {t("update.deltaSize", { size: fmtBytes(total) })}
              </span>
            </div>
            {showDetails && (
              <div
                className="max-h-32 overflow-y-auto rounded-md border bg-muted/40 p-2 text-xs"
                data-testid="update-details"
              >
                <div className="mb-1 font-semibold">{t("update.notesSummary")}</div>
                {check.notes_fa || check.notes_en || "—"}
              </div>
            )}
            <div className="flex flex-wrap gap-2">
              <Button onClick={start} data-testid="update-accept">
                {t("update.downloadInstall")}
              </Button>
              <Button variant="outline" onClick={onClose} data-testid="update-decline">
                {t("update.later")}
              </Button>
              <Button
                variant="ghost"
                onClick={() => setShowDetails((v) => !v)}
                data-testid="update-details-toggle"
              >
                {t("update.details")}
              </Button>
            </div>
          </>
        )}

        {(phase === "downloading" ||
          phase === "verifying" ||
          phase === "staged" ||
          phase === "applying") && (
          <div className="space-y-3">
            <div
              className="h-2 w-full overflow-hidden rounded-full bg-muted"
              data-testid="update-progress"
            >
              <div
                className="h-full bg-primary transition-all"
                style={{ width: `${phase === "downloading" ? pct : 100}%` }}
              />
            </div>
            <p className="text-sm" data-testid="update-progress-text">
              {phase === "downloading" &&
                t("update.downloadProgress", { done: fmtBytes(done), total: fmtBytes(total) })}
              {phase === "verifying" && t("update.verifying")}
              {phase === "staged" && t("update.verified")}
              {phase === "applying" && t("update.applying")}
            </p>
            {phase === "staged" && (
              <Button
                data-testid="update-apply"
                onClick={() =>
                  apply.mutate(undefined, {
                    onError: () => setPhase("failed"),
                  })
                }
              >
                {t("update.downloadInstall")}
              </Button>
            )}
          </div>
        )}

        {phase === "done" && (
          <div className="space-y-3">
            <p className="text-sm" data-testid="update-restart">
              {t("update.restart")}
            </p>
            <Button onClick={onClose} data-testid="update-finish">
              {t("actions.close")}
            </Button>
          </div>
        )}

        {phase === "failed" && (
          <div className="space-y-3">
            <p className="text-sm text-destructive" data-testid="update-failed">
              {errorFa || t("update.failed")}
            </p>
            {logPath && (
              <p className="num text-xs text-muted-foreground" data-testid="update-log-path">
                {t("update.logPath", { path: logPath })}
              </p>
            )}
            <Button variant="outline" onClick={onClose} data-testid="update-failed-close">
              {t("actions.close")}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
