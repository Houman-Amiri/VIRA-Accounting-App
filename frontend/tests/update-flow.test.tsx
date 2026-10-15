/** Real TanStack hooks + dialog; only the HTTP boundary is mocked (not useUpdateFlow). */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { api } from "@/api/client";
import { UpdateDialog } from "@/components/update-dialog";
import type { UpdateCheck, UpdateStatus } from "@/lib/update";

vi.mock("@/api/client", async (original) => {
  const actual = await original<typeof import("@/api/client")>();
  return { ...actual, api: { GET: vi.fn(), POST: vi.fn() } };
});

const check: UpdateCheck = {
  current: "1.0.6",
  latest: "1.0.7",
  update_available: true,
  checked: true,
  manual_required: false,
  choice: {
    kind: "delta",
    total_bytes: 100,
    packages: [
      {
        url: "https://github.com/x/y/d.zip",
        sha256: "ab".repeat(32),
        size: 100,
        from_version: "1.0.6",
      },
    ],
  },
};
const idle: UpdateStatus = {
  state: "idle",
  total_bytes: 100,
  downloaded_bytes: 0,
  verified: false,
  staged_path: "",
  log_path: "",
  machine_state: "idle",
};
const staged: UpdateStatus = {
  ...idle,
  state: "staged",
  downloaded_bytes: 100,
  verified: true,
  staged_path: "staging/payload",
};
const clients: QueryClient[] = [];
const success = (data: UpdateStatus) => ({ data, response: new Response(JSON.stringify(data)) });
const failure = (message: string, status = 403) => ({
  error: { detail: message },
  response: new Response(JSON.stringify({ detail: message, code: "sudo_required" }), { status }),
});

function mount(open = true): QueryClient {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  clients.push(client);
  render(
    <QueryClientProvider client={client}>
      <UpdateDialog check={check} open={open} onClose={() => {}} />
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  vi.mocked(api.GET)
    .mockReset()
    .mockResolvedValue(success(idle) as never);
  vi.mocked(api.POST).mockReset();
});
afterEach(() => {
  cleanup();
  clients.splice(0).forEach((client) => client.clear());
});

describe("0-byte update regression", () => {
  it("replaces cached idle with the POST result instead of remaining at 0 bytes", async () => {
    vi.mocked(api.POST).mockResolvedValue(success(staged) as never);
    const client = mount();
    await waitFor(() =>
      expect(client.getQueryData<UpdateStatus>(["update-status"])?.state).toBe("idle"),
    );
    fireEvent.click(screen.getByTestId("update-accept"));
    await waitFor(() => expect(screen.getByTestId("update-apply")).toBeInTheDocument());
    expect(client.getQueryData<UpdateStatus>(["update-status"])?.downloaded_bytes).toBe(100);
  });

  it("polls during a pending POST even when the first status was idle", async () => {
    let finish!: (value: never) => void;
    vi.mocked(api.POST).mockImplementation(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const client = mount();
    await waitFor(() =>
      expect(client.getQueryData<UpdateStatus>(["update-status"])?.state).toBe("idle"),
    );
    vi.mocked(api.GET).mockResolvedValue(
      success({ ...idle, state: "downloading", downloaded_bytes: 10 }) as never,
    );
    fireEvent.click(screen.getByTestId("update-accept"));
    try {
      await waitFor(
        () => expect(screen.getByTestId("update-progress-text")).toHaveTextContent("10 B"),
        { timeout: 2500 },
      );
    } finally {
      finish(success(staged) as never);
    }
    await waitFor(() => expect(screen.getByTestId("update-apply")).toBeInTheDocument());
  });

  it("continues polling after the new background-download response", async () => {
    vi.mocked(api.POST).mockResolvedValue(success({ ...idle, state: "downloading" }) as never);
    const client = mount();
    await waitFor(() =>
      expect(client.getQueryData<UpdateStatus>(["update-status"])?.state).toBe("idle"),
    );
    fireEvent.click(screen.getByTestId("update-accept"));
    await waitFor(() =>
      expect(client.getQueryData<UpdateStatus>(["update-status"])?.state).toBe("downloading"),
    );
    vi.mocked(api.GET).mockResolvedValue(success(staged) as never);
    await waitFor(() => expect(screen.getByTestId("update-apply")).toBeInTheDocument(), {
      timeout: 2500,
    });
  });

  it("shows a backend download failure and its log instead of stale progress", async () => {
    vi.mocked(api.POST).mockResolvedValue(
      success({
        ...idle,
        state: "failed",
        error_fa: "مهلت دریافت بسته تمام شد",
        log_path: "updates/update.log",
      }) as never,
    );
    mount();
    fireEvent.click(screen.getByTestId("update-accept"));
    await waitFor(() =>
      expect(screen.getByTestId("update-failed")).toHaveTextContent("مهلت دریافت بسته تمام شد"),
    );
    expect(screen.getByTestId("update-log-path")).toHaveTextContent("updates/update.log");
    expect(screen.queryByTestId("update-progress")).not.toBeInTheDocument();
  });

  it("surfaces the Persian sudo/HTTP error from the POST", async () => {
    vi.mocked(api.POST).mockResolvedValue(failure("احراز هویت مجدد لازم است") as never);
    mount();
    fireEvent.click(screen.getByTestId("update-accept"));
    await waitFor(() =>
      expect(screen.getByTestId("update-failed")).toHaveTextContent("احراز هویت مجدد لازم است"),
    );
  });

  it("surfaces status errors instead of silently keeping the progress screen", async () => {
    vi.mocked(api.GET).mockResolvedValue(failure("خواندن وضعیت ناموفق بود", 503) as never);
    mount();
    await waitFor(() =>
      expect(screen.getByTestId("update-failed")).toHaveTextContent("خواندن وضعیت ناموفق بود"),
    );
  });

  it("shows a Persian network message rather than a generic English error", async () => {
    vi.mocked(api.POST).mockRejectedValue(new TypeError("Failed to fetch"));
    mount();
    fireEvent.click(screen.getByTestId("update-accept"));
    await waitFor(() =>
      expect(screen.getByTestId("update-failed")).toHaveTextContent("اتصال شبکه"),
    );
  });

  it("does not poll a protected endpoint while the dialog is closed", () => {
    mount(false);
    expect(api.GET).not.toHaveBeenCalled();
  });
});
