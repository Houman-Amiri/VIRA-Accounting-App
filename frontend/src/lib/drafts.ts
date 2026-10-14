/**
 * Form-draft snapshot registry (Phase 5 §4).
 *
 * On 401 the API client snapshots every registered draft "in memory" and
 * persists it to sessionStorage so a /login round-trip loses nothing. After a
 * successful login the app restores drafts for the matching form keys.
 */

const STORAGE_KEY = "vira.draft-snapshots";

type SnapshotFn = () => unknown;

const registry = new Map<string, SnapshotFn>();

export function registerDraft(key: string, getSnapshot: SnapshotFn): () => void {
  registry.set(key, getSnapshot);
  return () => {
    registry.delete(key);
  };
}

export function snapshotDrafts(): void {
  const out: Record<string, unknown> = {};
  for (const [key, getSnapshot] of registry) {
    try {
      out[key] = getSnapshot();
    } catch {
      /* a broken form must not block the redirect */
    }
  }
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(out));
  } catch {
    /* storage full/private mode — in-memory snapshot already taken */
  }
}

export function loadDraft<T>(key: string): T | null {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const all = JSON.parse(raw) as Record<string, unknown>;
    return (all[key] as T) ?? null;
  } catch {
    return null;
  }
}

export function clearDraft(key: string): void {
  try {
    const raw = sessionStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    const all = JSON.parse(raw) as Record<string, unknown>;
    delete all[key];
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(all));
  } catch {
    /* ignore */
  }
}

export function clearAllDrafts(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}
