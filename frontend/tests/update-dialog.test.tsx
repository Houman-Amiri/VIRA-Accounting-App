/** Phase 8 §4 — update dialog: mandated Persian copy, decline path, progress,
 * restart step, rollback error + log path, startup badge. */
import * as React from "react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

const state: {
  checkData: unknown;
  statusData: {
    state: string;
    total_bytes: number;
    downloaded_bytes: number;
    verified: boolean;
    staged_path: string;
    log_path: string;
    error_fa: string | null;
    machine_state: string;
  };
  downloadImpl: () => void;
  applyImpl: () => void;
} = {
  checkData: null,
  statusData: {
    state: "idle",
    total_bytes: 250_000,
    downloaded_bytes: 0,
    verified: false,
    staged_path: "",
    log_path: "C:\\Users\\x\\AppData\\Local\\VIRA\\updates\\2.0.0\\update.log",
    error_fa: null,
    machine_state: "idle",
  },
  downloadImpl: () => {},
  applyImpl: () => {},
};

vi.mock("@/lib/update", () => ({
  useUpdateFlow: () => ({
    download: {
      mutate: () => {
        state.downloadImpl();
      },
    },
    apply: {
      mutate: () => {
        state.applyImpl();
      },
    },
    status: { data: state.statusData },
  }),
  useUpdateCheck: () => ({ data: state.checkData }),
}));

import { UpdateDialog } from "@/components/update-dialog";
import { useUpdateCheck } from "@/lib/update";

const CHECK = {
  current: "1.5.0",
  latest: "2.0.0",
  update_available: true,
  notes_fa: "نسخهٔ ۲ — رفع اشکال‌ها",
  notes_en: "v2",
  checked: true,
  reason: null,
  min_app_version: "1.0.0",
  manual_required: false,
  choice: {
    kind: "delta" as const,
    packages: [
      { url: "https://x/d.zip", sha256: "ab".repeat(32), size: 250_000, from_version: "1.5.0" },
    ],
    total_bytes: 250_000,
  },
};

function wrap(node: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{node}</QueryClientProvider>;
}

describe("UpdateDialog — mandated copy (§4)", () => {
  afterEach(cleanup);

  it("shows the exact title, message and three buttons in RTL", () => {
    render(wrap(<UpdateDialog check={CHECK as never} open onClose={() => {}} />));
    const dialog = screen.getByTestId("update-dialog");
    expect(dialog.getAttribute("dir")).toBe("rtl");
    expect(screen.getByTestId("update-dialog").textContent).toContain("به‌روزرسانی جدید موجود است");
    // exact mandated message «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z). آیا می‌خواهید دانلود و نصب شود؟»
    const msg = screen.getByTestId("update-message").textContent ?? "";
    expect(msg).toContain("به‌روزرسانی جدیدی در دسترس است");
    expect(msg).toContain("نسخهٔ 2.0.0");
    expect(msg).toContain("آیا می‌خواهید دانلود و نصب شود؟");
    expect(screen.getByTestId("update-accept").textContent).toContain("دانلود و نصب");
    expect(screen.getByTestId("update-decline").textContent).toContain("بعداً");
    expect(screen.getByTestId("update-details-toggle").textContent).toContain("مشاهدهٔ جزئیات");
    // delta badge + download size
    expect(screen.getByTestId("update-package-kind").textContent).toContain("بستهٔ تفاضلی");
    expect(screen.getByTestId("update-package-size").textContent).toContain("حجم دانلود");
  });

  it("decline path closes without downloading", () => {
    const onClose = vi.fn();
    render(wrap(<UpdateDialog check={CHECK as never} open onClose={onClose} />));
    fireEvent.click(screen.getByTestId("update-decline"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("«مشاهدهٔ جزئیات» reveals the release-notes summary", () => {
    render(wrap(<UpdateDialog check={CHECK as never} open onClose={() => {}} />));
    fireEvent.click(screen.getByTestId("update-details-toggle"));
    expect(screen.getByTestId("update-details").textContent).toContain("رفع اشکال‌ها");
  });

  it("accept starts the download and shows progress with sizes", () => {
    render(wrap(<UpdateDialog check={CHECK as never} open onClose={() => {}} />));
    fireEvent.click(screen.getByTestId("update-accept"));
    expect(screen.getByTestId("update-progress")).toBeTruthy();
    expect(screen.getByTestId("update-progress-text").textContent).toContain("دانلود");
    expect(screen.getByTestId("update-progress-text").textContent).toContain("244.1 KB");
  });

  it("failure shows the mandated rollback message with the log path", () => {
    state.statusData = {
      ...state.statusData,
      state: "failed",
      error_fa: null,
    };
    render(wrap(<UpdateDialog check={CHECK as never} open onClose={() => {}} />));
    expect(screen.getByTestId("update-failed").textContent).toContain(
      "خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.",
    );
    expect(screen.getByTestId("update-log-path").textContent).toContain("update.log");
  });

  it("restart-to-finish step appears after apply completes", () => {
    state.statusData = { ...state.statusData, state: "committed" };
    render(wrap(<UpdateDialog check={CHECK as never} open onClose={() => {}} />));
    expect(screen.getByTestId("update-restart").textContent).toContain(
      "برای تکمیل به‌روزرسانی، برنامه را دوباره راه‌اندازی کنید.",
    );
    state.statusData = { ...state.statusData, state: "idle" }; // reset
  });
});

describe("startup badge (§4)", () => {
  afterEach(cleanup);

  function BadgeProbe() {
    const { data } = useUpdateCheck();
    return <span data-testid="probe">{data?.update_available ? "badge" : "none"}</span>;
  }

  it("subtle badge state follows the background check result", async () => {
    state.checkData = { ...CHECK, update_available: true };
    render(wrap(<BadgeProbe />));
    await waitFor(() => expect(screen.getByTestId("probe").textContent).toBe("badge"));
    cleanup();
    state.checkData = { ...CHECK, update_available: false };
    render(wrap(<BadgeProbe />));
    await waitFor(() => expect(screen.getByTestId("probe").textContent).toBe("none"));
  });
});
