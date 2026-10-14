/**
 * <SearchFilterBar /> — Phase 7 §1: filter bar that calls the unified search
 * API (FTS5 + LIKE fallback, numeric tokens, RapidFuzz re-rank) and lists hits
 * inline with snippets. Used on the journal and account pages.
 */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";

import { api } from "@/api/client";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Search } from "lucide-react";

interface SearchHit {
  entity: string;
  ref_id: string;
  title: string;
  snippet: string;
  score: number;
}

export interface SearchFilterBarProps {
  /** Restrict to one entity ("all" for both entries and accounts). */
  entity?: "entry" | "account" | "all";
  placeholder?: string;
  "data-testid"?: string;
}

export function SearchFilterBar({
  entity = "all",
  placeholder = "جستجو در اسناد، حساب‌ها و مبالغ…",
  "data-testid": testId = "search-filter",
}: SearchFilterBarProps): React.JSX.Element {
  const [text, setText] = React.useState("");
  const trimmed = text.trim();

  const query = useQuery({
    queryKey: ["search", entity, trimmed],
    enabled: trimmed.length >= 2,
    staleTime: 30_000,
    queryFn: async () => {
      const res = await api.GET("/api/v1/search", {
        params: { query: { q: trimmed, entity, limit: 20 } },
      });
      return (res.data ?? { hits: [], backend: "none" }) as unknown as {
        hits: SearchHit[];
        backend: string;
      };
    },
  });

  const hits = trimmed.length >= 2 ? (query.data?.hits ?? []) : [];

  return (
    <div className="space-y-2" data-testid={testId}>
      <div className="relative">
        <Search className="absolute inset-y-0 start-3 h-4 w-4 text-muted-foreground" />
        <Input
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder={placeholder}
          className="ps-9"
          data-testid={`${testId}-input`}
        />
      </div>
      {query.isFetching && trimmed.length >= 2 && (
        <p className="text-xs text-muted-foreground">در حال جستجو…</p>
      )}
      {hits.length > 0 && (
        <ul className="space-y-1" data-testid={`${testId}-results`}>
          {hits.map((hit) => (
            <li
              key={`${hit.entity}:${hit.ref_id}`}
              className="flex items-center gap-2 rounded-md border px-3 py-2 text-sm"
              data-testid={`${testId}-hit`}
            >
              <Badge variant="secondary">{hit.entity === "account" ? "حساب" : "سند"}</Badge>
              <div className="flex-1">
                <div className="font-medium">{hit.title}</div>
                {hit.snippet && (
                  <div
                    className="text-xs text-muted-foreground"
                    // snippet is plain text (backend-built); never HTML
                  >
                    {hit.snippet}
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
      {trimmed.length >= 2 && !query.isFetching && hits.length === 0 && (
        <p className="text-sm text-muted-foreground" data-testid={`${testId}-empty`}>
          نتیجه‌ای یافت نشد.
        </p>
      )}
    </div>
  );
}
