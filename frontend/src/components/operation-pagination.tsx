import { faNumber } from "@/lib/fa";
export const OPERATION_PAGE_SIZE = 50;
export function OperationPagination({
  page,
  next,
  busy,
  onChange,
}: {
  page: number;
  next: boolean;
  busy: boolean;
  onChange: (page: number) => void;
}) {
  return (
    <nav
      aria-label="صفحه‌بندی فهرست"
      className="mt-3 flex items-center justify-between gap-2 text-xs"
    >
      <button
        type="button"
        className="rounded border px-3 py-2"
        disabled={page === 0 || busy}
        onClick={() => onChange(page - 1)}
      >
        صفحهٔ قبل
      </button>
      <span>صفحهٔ {faNumber(String(page + 1))}</span>
      <button
        type="button"
        className="rounded border px-3 py-2"
        disabled={!next || busy}
        onClick={() => onChange(page + 1)}
      >
        صفحهٔ بعد
      </button>
    </nav>
  );
}
