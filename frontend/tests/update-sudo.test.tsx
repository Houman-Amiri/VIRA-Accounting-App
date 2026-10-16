/** Actual sudo provider: expiry must prompt, never silently authorize or loop. */
import { afterEach, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api, clearSudoToken } from "@/api/client";
import { SudoProvider } from "@/components/sudo-dialog";
import { UpdateDialog } from "@/components/update-dialog";

vi.mock("@/api/client", async (original) => ({
  ...(await original<typeof import("@/api/client")>()),
  api: { GET: vi.fn(), POST: vi.fn() },
}));
afterEach(() => {
  cleanup();
  clearSudoToken();
  Reflect.deleteProperty(HTMLDialogElement.prototype, "showModal");
  Reflect.deleteProperty(HTMLDialogElement.prototype, "close");
  vi.restoreAllMocks();
});

it("re-authenticates an expired apply grant and retries only after user confirmation", async () => {
  Object.defineProperty(HTMLDialogElement.prototype, "showModal", {
    configurable: true,
    value: vi.fn(),
  });
  Object.defineProperty(HTMLDialogElement.prototype, "close", {
    configurable: true,
    value: vi.fn(),
  });
  const staged = {
    state: "staged",
    total_bytes: 100,
    downloaded_bytes: 100,
    verified: true,
    staged_path: "stage",
    log_path: "log",
    machine_state: "snapshotting",
  };
  vi.mocked(api.GET).mockResolvedValue({ data: staged, response: new Response() } as never);
  vi.mocked(api.POST)
    .mockResolvedValueOnce({
      error: { code: "sudo_required" },
      response: new Response(
        JSON.stringify({ code: "sudo_required", detail: "احراز هویت مجدد لازم است" }),
        { status: 403 },
      ),
    } as never)
    .mockResolvedValueOnce({
      data: { sudo_token: "test-step-up", expires_in_seconds: 300 },
      response: new Response(),
    } as never)
    .mockResolvedValueOnce({
      data: { ...staged, state: "committed" },
      response: new Response(),
    } as never);
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  try {
    render(
      <QueryClientProvider client={qc}>
        <SudoProvider>
          <UpdateDialog
            open
            onClose={() => {}}
            check={{
              current: "1.0.9",
              latest: "1.0.10",
              update_available: true,
              checked: true,
              manual_required: false,
              choice: {
                kind: "delta",
                total_bytes: 100,
                packages: [
                  {
                    url: "https://example.test/d.zip",
                    sha256: "ab".repeat(32),
                    size: 100,
                    from_version: "1.0.9",
                  },
                ],
              },
            }}
          />
        </SudoProvider>
      </QueryClientProvider>,
    );
    fireEvent.click(await screen.findByTestId("update-apply"));
    await waitFor(() => expect(api.POST).toHaveBeenCalledTimes(1));
    fireEvent.change(screen.getByTestId("sudo-password"), {
      target: { value: "dedicated-test-password" },
    });
    fireEvent.click(screen.getByTestId("sudo-confirm"));
    await screen.findByTestId("update-restart");
    expect(vi.mocked(api.POST).mock.calls.map(([url]) => url)).toEqual([
      "/api/v1/system/update/apply",
      "/api/v1/auth/sudo",
      "/api/v1/system/update/apply",
    ]);
  } finally {
    qc.clear();
  }
});
