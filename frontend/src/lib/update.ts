/**
 * Update channel — typed client for Phase 8 §3/§4.
 *
 * Zod-validated parsing of the update-check response (which wraps the
 * schema_version'd latest.json), TanStack Query hooks for the startup badge
 * and the «بررسی به‌روزرسانی» flow, and the download/apply calls that drive
 * the transactional updater helper.
 */
import { useRef } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api, ApiError, parseError } from "@/api/client";

export const UpdatePackageSchema = z.object({
  url: z.string().url().or(z.string().startsWith("/")),
  sha256: z.string().length(64),
  size: z.number().int().nonnegative(),
  from_version: z.string(),
});

export const UpdateChoiceSchema = z.object({
  kind: z.enum(["delta", "delta_chain", "full"]),
  packages: z.array(UpdatePackageSchema),
  total_bytes: z.number().int().nonnegative(),
});

export const UpdateCheckSchema = z.object({
  current: z.string(),
  latest: z.string().nullable(),
  update_available: z.boolean(),
  notes_fa: z.string().nullable().optional(),
  notes_en: z.string().nullable().optional(),
  checked: z.boolean(),
  reason: z.string().nullable().optional(),
  min_app_version: z.string().nullable().optional(),
  manual_required: z.boolean().optional().default(false),
  choice: UpdateChoiceSchema.nullable().optional(),
});

export const UpdateStatusSchema = z.object({
  target_version: z.string().optional(),
  state: z.enum([
    "idle",
    "downloading",
    "verifying",
    "staged",
    "applying",
    "committed",
    "rolled_back",
    "failed",
  ]),
  total_bytes: z.number().int().nonnegative(),
  downloaded_bytes: z.number().int().nonnegative(),
  verified: z.boolean(),
  staged_path: z.string(),
  log_path: z.string(),
  error_fa: z.string().nullable().optional(),
  machine_state: z.string(),
});

export type UpdateCheck = z.infer<typeof UpdateCheckSchema>;
export type UpdateStatus = z.infer<typeof UpdateStatusSchema>;

export async function fetchUpdateCheck(): Promise<UpdateCheck> {
  const res = await api.GET("/api/v1/system/check-updates");
  if (res.error) {
    // Surface the server's Persian RFC 9457 detail instead of a bare
    // «check failed» — v1.0.4 hid a real SemVer crash behind that string.
    throw await parseError(res.response);
  }
  return UpdateCheckSchema.parse(res.data);
}

export function useUpdateCheck(enabled = true) {
  return useQuery({
    queryKey: ["update-check"],
    queryFn: fetchUpdateCheck,
    enabled,
    staleTime: 5 * 60_000,
    retry: 1,
  });
}

export async function fetchUpdateStatus(): Promise<UpdateStatus> {
  const res = await api.GET("/api/v1/system/update/status");
  if (res.error) throw await parseError(res.response);
  return UpdateStatusSchema.parse(res.data);
}

export function useUpdateFlow(enabled = true, requestSudo?: (() => Promise<string>) | null) {
  async function withSudo<T>(action: () => Promise<T>): Promise<T> {
    try {
      return await action();
    } catch (error) {
      if (!(error instanceof ApiError) || !error.needsSudo || !requestSudo) throw error;
      await requestSudo();
      return action(); // once, after explicit step-up; never an automatic permission bypass
    }
  }
  const qc = useQueryClient();
  const applyingSince = useRef<number | null>(null);
  const awaitingRestart = () =>
    applyingSince.current !== null && Date.now() - applyingSince.current < 240_000;
  const storeStatus = async (data: UpdateStatus): Promise<void> => {
    // A status GET started before the mutation must not overwrite its result.
    await qc.cancelQueries({ queryKey: ["update-status"] });
    qc.setQueryData(["update-status"], data);
  };
  const download = useMutation({
    mutationFn: (approval: {
      expected_version: string;
      expected_sha256: string;
    }): Promise<UpdateStatus> =>
      withSudo(async () => {
        const res = await api.POST("/api/v1/system/update/download", { body: approval });
        if (res.error) throw await parseError(res.response);
        return UpdateStatusSchema.parse(res.data);
      }),
    onSuccess: storeStatus,
  });
  const apply = useMutation({
    onMutate: () => {
      applyingSince.current = Date.now();
    },
    onError: () => {
      applyingSince.current = null;
    },
    mutationFn: (): Promise<UpdateStatus> =>
      withSudo(async () => {
        const res = await api.POST("/api/v1/system/update/apply", {});
        if (res.error) throw await parseError(res.response);
        return UpdateStatusSchema.parse(res.data);
      }),
    onSuccess: async (data) => {
      await storeStatus(data);
      void qc.invalidateQueries({ queryKey: ["update-check"] });
    },
  });
  const status = useQuery({
    queryKey: ["update-status"],
    enabled,
    retry: false,
    refetchIntervalInBackground: true,
    queryFn: async () => {
      const data = await fetchUpdateStatus();
      if (["committed", "rolled_back", "failed"].includes(data.state)) applyingSince.current = null;
      return data;
    },
    refetchInterval: (query) => {
      const s = query.state.data;
      const busy =
        awaitingRestart() ||
        download.isPending ||
        apply.isPending ||
        (s && ["downloading", "verifying", "applying"].includes(s.state));
      return enabled && busy ? 700 : false;
    },
  });
  return { download, apply, status, reconnecting: awaitingRestart() };
}
