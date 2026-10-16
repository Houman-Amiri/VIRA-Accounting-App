import type { ReactNode } from "react";

/** Never label a failed/loading operations query as a healthy empty list. */
export function QueryNotice({
  query,
}: {
  query: { isPending: boolean; isError: boolean; isFetching: boolean; refetch: () => unknown };
}): ReactNode {
  if (query.isError)
    return (
      <div role="alert" className="my-2 text-sm text-destructive">
        دریافت داده ناموفق بود؛ وضعیت نامشخص است.{" "}
        <button
          type="button"
          disabled={query.isFetching}
          className="rounded border px-2 py-1"
          onClick={() => void query.refetch()}
        >
          تلاش دوباره
        </button>
      </div>
    );
  if (query.isPending)
    return (
      <p role="status" className="my-2 text-sm text-muted-foreground">
        در حال دریافت داده…
      </p>
    );
  return null;
}
