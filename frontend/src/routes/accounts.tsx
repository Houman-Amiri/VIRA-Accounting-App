/** چارت حساب‌ها — hierarchical tree table (expand/collapse, depth indent). */
import * as React from "react";
import { useQuery } from "@tanstack/react-query";
import { SearchFilterBar } from "@/components/search-filter-bar";
import { api, parseError } from "@/api/client";
import { Badge } from "@/components/ui/badge";
import { ChevronDown, ChevronLeft } from "lucide-react";

interface AccountNode {
  id: string;
  code: string;
  name: string;
  kind: string;
  parent_id: string | null;
  is_placeholder: boolean;
  children?: AccountNode[];
}

export function AccountsPage(): React.JSX.Element {
  const [collapsed, setCollapsed] = React.useState<Set<string>>(new Set());
  const accountsQuery = useQuery({
    queryKey: ["accounts", "tree"],
    queryFn: async () => {
      const res = await api.GET("/api/v1/accounts");
      if (res.error) throw await parseError(res.response);
      return res.data as unknown as AccountNode[];
    },
  });

  const rows = React.useMemo(() => {
    const accounts = accountsQuery.data ?? [];
    const byParent = new Map<string | null, AccountNode[]>();
    for (const a of accounts) {
      const list = byParent.get(a.parent_id) ?? [];
      list.push(a);
      byParent.set(a.parent_id, list);
    }
    const flat: Array<{ node: AccountNode; depth: number }> = [];
    const walk = (parentId: string | null, depth: number): void => {
      for (const node of byParent.get(parentId) ?? []) {
        flat.push({ node, depth });
        if (!collapsed.has(node.id)) walk(node.id, depth + 1);
      }
    };
    walk(null, 0);
    return flat;
  }, [accountsQuery.data, collapsed]);

  return (
    <div className="space-y-4" dir="rtl">
      <h1 className="text-xl font-bold">چارت حساب‌ها</h1>
      <SearchFilterBar entity="account" data-testid="accounts-search" />
      <div className="rounded-lg border bg-card">
        {rows.map(({ node, depth }) => {
          const hasChildren = (accountsQuery.data ?? []).some((a) => a.parent_id === node.id);
          return (
            <div
              key={node.id}
              className="flex items-center gap-2 border-b px-3 py-2 text-sm last:border-b-0 hover:bg-muted/50"
              style={{ paddingInlineStart: `${depth * 1.5 + 0.75}rem` }}
            >
              {hasChildren ? (
                <button
                  type="button"
                  aria-label={collapsed.has(node.id) ? "باز کردن" : "بستن"}
                  onClick={() =>
                    setCollapsed((prev) => {
                      const next = new Set(prev);
                      if (next.has(node.id)) next.delete(node.id);
                      else next.add(node.id);
                      return next;
                    })
                  }
                >
                  {collapsed.has(node.id) ? (
                    <ChevronLeft className="h-4 w-4" />
                  ) : (
                    <ChevronDown className="h-4 w-4" />
                  )}
                </button>
              ) : (
                <span className="w-4" />
              )}
              <span className="num text-muted-foreground">{node.code}</span>
              <span className="font-medium">{node.name}</span>
              {node.is_placeholder && <Badge variant="outline">کمکی</Badge>}
              <Badge variant="secondary" className="ms-auto">
                {node.kind}
              </Badge>
            </div>
          );
        })}
        {rows.length === 0 && (
          <div className="p-8 text-center text-muted-foreground">در حال بارگذاری…</div>
        )}
      </div>
    </div>
  );
}
