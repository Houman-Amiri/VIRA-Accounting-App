/** Login page (Phase 5 §4) — RTL Persian, redirects to the app after login. */
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { api, ApiError, parseError, setSudoToken } from "@/api/client";
import { clearAllDrafts } from "@/lib/drafts";

export function LoginPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await api.POST("/api/v1/auth/login", {
        body: { username, password },
      });
      if (res.error) {
        const err = await parseError(res.response);
        setError(
          err.status === 429
            ? "تعداد تلاش‌های ورود بیش از حد مجاز است؛ لطفاً کمی بعد دوباره تلاش کنید."
            : "نام کاربری یا رمز عبور نادرست است.",
        );
        return;
      }
      clearAllDrafts(); // fresh session; unsaved drafts restored per-form instead
      void setSudoToken; // no-op reference; sudo handled separately
      void navigate({ to: "/" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "خطای غیرمنتظره رخ داد.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background p-4" dir="rtl">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-xl border bg-card p-6 shadow-sm"
      >
        <div className="text-center">
          <div className="mx-auto mb-2 flex h-11 w-11 items-center justify-center rounded-lg bg-primary text-primary-foreground text-xl font-bold">
            و
          </div>
          <h1 className="text-lg font-bold">حسابداری ویرا</h1>
          <p className="text-xs text-muted-foreground">برای ادامه وارد شوید</p>
        </div>
        <label className="block space-y-1">
          <span className="text-sm">نام کاربری</span>
          <input
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoComplete="username"
            required
          />
        </label>
        <label className="block space-y-1">
          <span className="text-sm">رمز عبور</span>
          <input
            type="password"
            className="w-full rounded-md border bg-background px-3 py-2 text-sm"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </label>
        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-primary px-3 py-2 text-sm font-medium text-primary-foreground disabled:opacity-60"
        >
          {busy ? "در حال ورود…" : "ورود"}
        </button>
      </form>
    </div>
  );
}
