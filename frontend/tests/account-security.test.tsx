import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { AccountSecuritySettings } from "@/components/account-security-settings";

const clients: QueryClient[] = [];

function mount() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, staleTime: Infinity }, mutations: { retry: false } },
  });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <AccountSecuritySettings />
    </QueryClientProvider>,
  );
  return client;
}

function ok(data: unknown) {
  return { data, response: new Response() } as never;
}

function failure(status: number, body: Record<string, unknown>) {
  return {
    error: body,
    response: new Response(JSON.stringify(body), {
      status,
      headers: { "content-type": "application/json" },
    }),
  } as never;
}

beforeEach(() => {
  vi.spyOn(api, "GET").mockResolvedValue(ok({ user_id: "u1", username: "owner", role: "OWNER" }));
});

afterEach(() => {
  cleanup();
  clients.splice(0).forEach((c) => c.clear());
  vi.restoreAllMocks();
});

it("shows the current login name from the session", async () => {
  mount();
  await waitFor(() =>
    expect(screen.getByTestId("current-username")).toHaveTextContent("نام کاربری فعلی: owner"),
  );
});

it("renames the login to NOA and reports the new name", async () => {
  const put = vi
    .spyOn(api, "PUT")
    .mockResolvedValue(ok({ user_id: "u1", username: "NOA", role: "OWNER" }));
  mount();
  await screen.findByTestId("current-username");
  fireEvent.change(screen.getByTestId("new-username"), { target: { value: "NOA" } });
  fireEvent.change(screen.getByTestId("username-password"), {
    target: { value: "test-password-1" },
  });
  fireEvent.click(screen.getByTestId("rename-submit"));
  await waitFor(() => expect(put).toHaveBeenCalledOnce());
  expect(put).toHaveBeenCalledWith("/api/v1/auth/username", {
    body: { username: "NOA", password: "test-password-1" },
  });
  expect(await screen.findByTestId("rename-status")).toHaveTextContent("NOA");
});

it("will not rename to the name that is already yours", async () => {
  mount();
  await screen.findByTestId("current-username");
  fireEvent.change(screen.getByTestId("new-username"), { target: { value: "owner" } });
  fireEvent.change(screen.getByTestId("username-password"), {
    target: { value: "test-password-1" },
  });
  expect(screen.getByTestId("rename-submit")).toBeDisabled();
});

it("shows the server's Persian reason when the current password is wrong", async () => {
  const put = vi
    .spyOn(api, "PUT")
    .mockResolvedValue(failure(403, { code: "wrong_password", detail: "رمز فعلی درست نیست." }));
  mount();
  await screen.findByTestId("current-username");
  fireEvent.change(screen.getByTestId("new-username"), { target: { value: "NOA" } });
  fireEvent.change(screen.getByTestId("username-password"), { target: { value: "wrong" } });
  fireEvent.click(screen.getByTestId("rename-submit"));
  expect(await screen.findByTestId("rename-error")).toHaveTextContent("رمز فعلی درست نیست.");
  expect(put).toHaveBeenCalledOnce();
});

it("changes the password only when both entries match and are long enough", async () => {
  const post = vi
    .spyOn(api, "POST")
    .mockResolvedValue(ok({ user_id: "u1", username: "owner", role: "OWNER" }));
  mount();
  await screen.findByTestId("current-username");
  fireEvent.change(screen.getByTestId("current-password"), {
    target: { value: "test-password-1" },
  });
  fireEvent.change(screen.getByTestId("new-password"), { target: { value: "short" } });
  fireEvent.change(screen.getByTestId("repeat-password"), { target: { value: "short" } });
  expect(screen.getByTestId("password-submit")).toBeDisabled();

  fireEvent.change(screen.getByTestId("new-password"), { target: { value: "540210.321" } });
  expect(screen.getByTestId("password-submit")).toBeDisabled();
  expect(screen.getByTestId("password-mismatch")).toBeInTheDocument();

  fireEvent.change(screen.getByTestId("repeat-password"), { target: { value: "540210.321" } });
  expect(screen.getByTestId("password-submit")).toBeEnabled();
  fireEvent.click(screen.getByTestId("password-submit"));

  await waitFor(() => expect(post).toHaveBeenCalledOnce());
  expect(post).toHaveBeenCalledWith("/api/v1/auth/password", {
    body: { current_password: "test-password-1", new_password: "540210.321" },
  });
  expect(await screen.findByTestId("password-status")).toHaveTextContent("رمز عبور تغییر کرد");
  // the typed passwords are cleared from the form once they are stored
  expect(screen.getByTestId("new-password")).toHaveValue("");
});

it("never renders the new password back to the page", async () => {
  vi.spyOn(api, "POST").mockResolvedValue(ok({ user_id: "u1", username: "owner", role: "OWNER" }));
  mount();
  await screen.findByTestId("current-username");
  fireEvent.change(screen.getByTestId("current-password"), {
    target: { value: "test-password-1" },
  });
  fireEvent.change(screen.getByTestId("new-password"), { target: { value: "540210.321" } });
  fireEvent.change(screen.getByTestId("repeat-password"), { target: { value: "540210.321" } });
  fireEvent.click(screen.getByTestId("password-submit"));
  await screen.findByTestId("password-status");
  expect(document.body.textContent).not.toContain("540210.321");
});
