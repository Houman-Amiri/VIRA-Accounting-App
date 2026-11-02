/**
 * «امنیت و ورود» — the login name and the password, changed by the owner.
 *
 * Before v1.0.16 neither could be changed inside the app: the password was
 * generated on the first start and only an offline script could replace it.
 * Both forms here ask for the *current* password, so an unattended browser
 * window cannot lock the owner out of their own books.
 */
import * as React from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, parseError } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

const MIN_PASSWORD = 8;

function errText(error: unknown): string {
  if (error instanceof Error && error.message) return error.message;
  return "درخواست انجام نشد؛ دوباره تلاش کنید.";
}

async function readError(res: { error?: unknown; response: Response }): Promise<never> {
  throw await parseError(res.response as Response);
}

export function AccountSecuritySettings(): React.JSX.Element {
  const queryClient = useQueryClient();
  const user = useQuery({
    queryKey: ["session-user"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/auth/me");
      if (res.error) await readError(res);
      return res.data;
    },
  });

  const [usernameDraft, setUsernameDraft] = React.useState("");
  const [usernamePassword, setUsernamePassword] = React.useState("");
  const [usernameMessage, setUsernameMessage] = React.useState<string | null>(null);
  const [usernameError, setUsernameError] = React.useState<string | null>(null);

  const [currentPassword, setCurrentPassword] = React.useState("");
  const [newPassword, setNewPassword] = React.useState("");
  const [repeatPassword, setRepeatPassword] = React.useState("");
  const [passwordMessage, setPasswordMessage] = React.useState<string | null>(null);
  const [passwordError, setPasswordError] = React.useState<string | null>(null);

  const rename = useMutation({
    mutationFn: async () => {
      const res = await api.PUT("/api/v1/auth/username", {
        body: { username: usernameDraft.trim(), password: usernamePassword },
      });
      if (res.error) await readError(res);
      return res.data;
    },
    onSuccess: (data) => {
      setUsernameDraft("");
      setUsernamePassword("");
      setUsernameError(null);
      setUsernameMessage(`نام کاربری به «${data?.username ?? ""}» تغییر کرد.`);
      void queryClient.invalidateQueries({ queryKey: ["session-user"] });
    },
    onError: (error) => {
      setUsernameMessage(null);
      setUsernameError(errText(error));
    },
  });

  const changePassword = useMutation({
    mutationFn: async () => {
      const res = await api.POST("/api/v1/auth/password", {
        body: { current_password: currentPassword, new_password: newPassword },
      });
      if (res.error) await readError(res);
      return res.data;
    },
    onSuccess: () => {
      setCurrentPassword("");
      setNewPassword("");
      setRepeatPassword("");
      setPasswordError(null);
      setPasswordMessage("رمز عبور تغییر کرد. از این به بعد با رمز تازه وارد شوید.");
    },
    onError: (error) => {
      setPasswordMessage(null);
      setPasswordError(errText(error));
    },
  });

  const mismatch = repeatPassword.length > 0 && repeatPassword !== newPassword;
  const passwordBlocked =
    changePassword.isPending ||
    !currentPassword ||
    newPassword.length < MIN_PASSWORD ||
    repeatPassword !== newPassword;
  const renameBlocked =
    rename.isPending ||
    !usernamePassword ||
    usernameDraft.trim().length < 3 ||
    usernameDraft.trim() === (user.data?.username ?? "");

  return (
    <Card id="account-security" data-testid="account-security">
      <CardHeader>
        <CardTitle>امنیت و ورود</CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <p className="text-sm text-muted-foreground" data-testid="current-username">
          {user.isPending
            ? "در حال خواندن نام کاربری…"
            : `نام کاربری فعلی: ${user.data?.username ?? "—"}`}
        </p>

        <form
          className="space-y-2 rounded-md border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            setUsernameMessage(null);
            setUsernameError(null);
            rename.mutate();
          }}
        >
          <h3 className="text-sm font-semibold">تغییر نام کاربری</h3>
          <p className="text-xs text-muted-foreground">
            با همین نام وارد می‌شوید. حروف انگلیسی، رقم، نقطه، خط تیره و زیرخط؛ ۳ تا ۳۲ نویسه.
          </p>
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1">
              <Label htmlFor="new-username">نام کاربری تازه</Label>
              <Input
                id="new-username"
                data-testid="new-username"
                autoComplete="username"
                value={usernameDraft}
                onChange={(event) => {
                  setUsernameDraft(event.target.value);
                  setUsernameMessage(null);
                }}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="username-password">رمز فعلی</Label>
              <Input
                id="username-password"
                data-testid="username-password"
                type="password"
                autoComplete="current-password"
                value={usernamePassword}
                onChange={(event) => {
                  setUsernamePassword(event.target.value);
                  setUsernameMessage(null);
                }}
              />
            </div>
          </div>
          <Button type="submit" size="sm" disabled={renameBlocked} data-testid="rename-submit">
            ذخیرهٔ نام کاربری
          </Button>
          {usernameError && (
            <p role="alert" className="text-sm text-destructive" data-testid="rename-error">
              {usernameError}
            </p>
          )}
          {usernameMessage && (
            <p role="status" className="text-sm text-positive" data-testid="rename-status">
              {usernameMessage}
            </p>
          )}
        </form>

        <form
          className="space-y-2 rounded-md border p-3"
          onSubmit={(event) => {
            event.preventDefault();
            setPasswordMessage(null);
            setPasswordError(null);
            changePassword.mutate();
          }}
        >
          <h3 className="text-sm font-semibold">تغییر رمز عبور</h3>
          <p className="text-xs text-muted-foreground">
            حداقل {MIN_PASSWORD} نویسه. برای امنیت، رمز فعلی هم پرسیده می‌شود؛ رمز تازه هیچ‌جا ذخیره
            یا نمایش داده نمی‌شود.
          </p>
          <div className="grid gap-2 sm:grid-cols-3">
            <div className="space-y-1">
              <Label htmlFor="current-password">رمز فعلی</Label>
              <Input
                id="current-password"
                data-testid="current-password"
                type="password"
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => {
                  setCurrentPassword(event.target.value);
                  setPasswordMessage(null);
                }}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="new-password">رمز تازه</Label>
              <Input
                id="new-password"
                data-testid="new-password"
                type="password"
                autoComplete="new-password"
                value={newPassword}
                onChange={(event) => {
                  setNewPassword(event.target.value);
                  setPasswordMessage(null);
                }}
              />
            </div>
            <div className="space-y-1">
              <Label htmlFor="repeat-password">تکرار رمز تازه</Label>
              <Input
                id="repeat-password"
                data-testid="repeat-password"
                type="password"
                autoComplete="new-password"
                value={repeatPassword}
                onChange={(event) => {
                  setRepeatPassword(event.target.value);
                  setPasswordMessage(null);
                }}
              />
            </div>
          </div>
          {mismatch && (
            <p role="alert" className="text-sm text-destructive" data-testid="password-mismatch">
              دو رمز تازه یکسان نیستند.
            </p>
          )}
          <Button type="submit" size="sm" disabled={passwordBlocked} data-testid="password-submit">
            ذخیرهٔ رمز تازه
          </Button>
          {passwordError && (
            <p role="alert" className="text-sm text-destructive" data-testid="password-error">
              {passwordError}
            </p>
          )}
          {passwordMessage && (
            <p role="status" className="text-sm text-positive" data-testid="password-status">
              {passwordMessage}
            </p>
          )}
          <p className="text-xs text-muted-foreground">
            نشست‌هایی که همین حالا در مرورگر بازند تا پایان عمرشان (حداکثر ۱۲ ساعت) معتبر می‌مانند؛
            برای بستن همهٔ آن‌ها، برنامه را ببندید و فایل
            <span className="num"> %LOCALAPPDATA%\NOA\session.secret </span>
            را پاک کنید.
          </p>
        </form>
      </CardContent>
    </Card>
  );
}
