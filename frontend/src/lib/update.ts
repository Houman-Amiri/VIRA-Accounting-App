/**
 * Update channel — typed client for Phase 8 §3/§4.
 *
 * Zod-validated parsing of the update-check response (which wraps the
 * schema_version'd latest.json), TanStack Query hooks for the startup badge
 * and the «بررسی به‌روزرسانی» flow, and the download/apply calls that drive
 * the transactional updater helper.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { z } from "zod";

import { api } from "@/api/client";

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
  if (res.error) throw new Error("check failed");
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

export function useUpdateFlow() {
  const qc = useQueryClient();
  const download = useMutation({
    mutationFn: async (): Promise<UpdateStatus> => {
      const res = await api.POST("/api/v1/system/update/download", {});
      if (res.error) throw new Error("download failed");
      return UpdateStatusSchema.parse(res.data);
    },
  });
  const apply = useMutation({
    mutationFn: async (): Promise<UpdateStatus> => {
      const res = await api.POST("/api/v1/system/update/apply", {});
      if (res.error) throw new Error("apply failed");
      return UpdateStatusSchema.parse(res.data);
    },
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["update-check"] });
    },
  });
  const status = useQuery({
    queryKey: ["update-status"],
    queryFn: async (): Promise<UpdateStatus> => {
      const res = await api.GET("/api/v1/system/update/status");
      if (res.error) throw new Error("status failed");
      return UpdateStatusSchema.parse(res.data);
    },
    refetchInterval: (query) => {
      const s = query.state.data;
      return s && (s.state === "downloading" || s.state === "verifying" || s.state === "applying")
        ? 700
        : false;
    },
  });
  return { download, apply, status };
}
