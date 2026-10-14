/** Phase 5 §4 — draft snapshot registry survives a 401→login round-trip. */
import { beforeEach, describe, expect, it } from "vitest";
import { clearAllDrafts, clearDraft, loadDraft, registerDraft, snapshotDrafts } from "@/lib/drafts";

describe("draft snapshots", () => {
  beforeEach(() => {
    clearAllDrafts();
  });

  it("snapshots registered drafts and restores them by key", () => {
    registerDraft("journal-new", () => ({ description: "خرید", splits: [1, 2] }));
    snapshotDrafts();
    expect(loadDraft<{ description: string }>("journal-new")?.description).toBe("خرید");
  });

  it("clears one draft without touching others", () => {
    registerDraft("a", () => ({ v: 1 }));
    registerDraft("b", () => ({ v: 2 }));
    snapshotDrafts();
    clearDraft("a");
    expect(loadDraft("a")).toBeNull();
    expect(loadDraft("b")).toEqual({ v: 2 });
  });

  it("tolerates broken snapshot functions", () => {
    registerDraft("broken", () => {
      throw new Error("boom");
    });
    expect(() => snapshotDrafts()).not.toThrow();
    expect(loadDraft("broken")).toBeNull();
  });
});
