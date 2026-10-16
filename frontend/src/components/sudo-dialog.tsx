/**
 * Sudo step-up dialog (Phase 5 §2) — password re-entry to obtain a 5-minute
 * sudo token for high-risk actions (API keys, period reopen, dump export,
 * un-reconcile). `requestSudo()` resolves with a fresh token or rejects.
 */
import { createContext, useCallback, useContext, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { api, parseError, setSudoToken } from "@/api/client";

type SudoFn = () => Promise<string>;

const SudoContext = createContext<SudoFn | null>(null);

export function useOptionalRequestSudo(): SudoFn | null {
  return useContext(SudoContext);
}

export function useRequestSudo(): SudoFn {
  const fn = useContext(SudoContext);
  if (!fn) throw new Error("SudoProvider missing");
  return fn;
}

interface SudoResponseBody {
  sudo_token: string;
  expires_in_seconds: number;
}

export function SudoProvider({ children }: { children: React.ReactNode }) {
  const { t } = useTranslation();
  const [pending, setPending] = useState<{
    resolve: (token: string) => void;
    reject: (err: Error) => void;
  } | null>(null);
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const dialogRef = useRef<HTMLDialogElement>(null);

  const requestSudo = useCallback<SudoFn>(() => {
    return new Promise<string>((resolve, reject) => {
      setPending({ resolve, reject });
      setPassword("");
      setError(null);
      setTimeout(() => dialogRef.current?.showModal(), 0);
    });
  }, []);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!pending) return;
    setBusy(true);
    setError(null);
    try {
      const res = await api.POST("/api/v1/auth/sudo", {
        body: { password, totp_code: null },
      });
      if (res.error || !res.data) {
        const err = await parseError(res.response);
        setError(err.status === 403 ? t("sudo.wrongPassword") : err.message);
        return;
      }
      const data = res.data as SudoResponseBody;
      setSudoToken(data.sudo_token, data.expires_in_seconds);
      dialogRef.current?.close();
      pending.resolve(data.sudo_token);
      setPending(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : t("errors.generic"));
    } finally {
      setBusy(false);
    }
  }

  function cancel() {
    dialogRef.current?.close();
    pending?.reject(new Error("sudo cancelled"));
    setPending(null);
  }

  return (
    <SudoContext.Provider value={requestSudo}>
      {children}
      <dialog
        data-testid="sudo-dialog"
        ref={dialogRef}
        dir="rtl"
        className="m-auto w-full max-w-sm rounded-xl border bg-card p-0 shadow-lg backdrop:bg-black/40"
        onCancel={(e) => {
          e.preventDefault();
          cancel();
        }}
      >
        <form onSubmit={submit} className="space-y-4 p-6">
          <h2 className="text-base font-bold">{t("sudo.title")}</h2>
          <p className="text-sm text-muted-foreground">{t("sudo.prompt")}</p>
          <input
            data-testid="sudo-password"
            type="password"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            autoFocus
            required
          />
          {error && (
            <p
              className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive"
              role="alert"
            >
              {error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <button type="button" onClick={cancel} className="rounded-md border px-3 py-2 text-sm">
              انصراف
            </button>
            <button
              data-testid="sudo-confirm"
              type="submit"
              disabled={busy}
              className="rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
            >
              {busy ? t("sudo.busy") : t("sudo.confirm")}
            </button>
          </div>
        </form>
      </dialog>
    </SudoContext.Provider>
  );
}
