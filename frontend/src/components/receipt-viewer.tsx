/**
 * <ReceiptViewer /> — faceted receipt viewer (Phase 7 §2).
 *
 * Two facets by content type:
 *  - images: full zoom / rotate / pan via react-zoom-pan-pinch
 *  - PDF:    react-pdf page surface with faceted page navigation (_prev/_next);
 *            zoom / rotate / pan applies to the page surface.
 *
 * S3 mode: the API redirects (302) to a short-lived presigned GET, so the
 * same authenticated URL works for <img>, fetch and react-pdf alike.
 */
import * as React from "react";
import { TransformComponent, TransformWrapper } from "react-zoom-pan-pinch";
import { Document, Page, pdfjs } from "react-pdf";

import { Button } from "@/components/ui/button";
import { cn } from "@/lib/cn";
import { ChevronLeft, ChevronRight, RotateCw, ZoomIn, ZoomOut } from "lucide-react";

pdfjs.GlobalWorkerOptions.workerSrc = new URL(
  "pdfjs-dist/build/pdf.worker.min.mjs",
  import.meta.url,
).toString();

export interface ReceiptViewerProps {
  /** Authenticated URL (may 302 to a presigned origin). */
  url: string;
  mediaType?: string;
  className?: string;
}

function isPdf(url: string, mediaType?: string): boolean {
  return mediaType === "application/pdf" || url.split("?")[0].toLowerCase().endsWith(".pdf");
}

export function ReceiptViewer({
  url,
  mediaType,
  className,
}: ReceiptViewerProps): React.JSX.Element {
  const [pageCount, setPageCount] = React.useState(1);
  const [page, _setPage] = React.useState(1);
  const [rotation, setRotation] = React.useState(0);
  const [error, setError] = React.useState(false);
  const pdf = isPdf(url, mediaType);

  const _next = React.useCallback(() => _setPage((p) => Math.min(p + 1, pageCount)), [pageCount]);
  const _prev = React.useCallback(() => _setPage((p) => Math.max(p - 1, 1)), []);

  return (
    <div className={cn("space-y-2", className)} data-testid="receipt-viewer">
      {/* Faceted toolbar: zoom / rotate / (pdf) page flips */}
      <div className="flex items-center justify-between print:hidden">
        <div className="flex items-center gap-1">
          {pdf && (
            <>
              <Button
                size="icon"
                variant="outline"
                aria-label="صفحه قبل"
                data-testid="viewer-prev"
                disabled={page <= 1}
                onClick={_prev}
              >
                <ChevronRight />
              </Button>
              <span className="num text-sm" data-testid="viewer-page">
                {page} / {pageCount}
              </span>
              <Button
                size="icon"
                variant="outline"
                aria-label="صفحه بعد"
                data-testid="viewer-next"
                disabled={page >= pageCount}
                onClick={_next}
              >
                <ChevronLeft />
              </Button>
            </>
          )}
        </div>
      </div>

      {error && <p className="text-sm text-destructive">خطا در بارگذاری رسید</p>}

      <TransformWrapper minScale={0.25} maxScale={8} doubleClick={{ mode: "toggle" }}>
        {({ zoomIn, zoomOut }) => (
          <>
            <div className="flex items-center gap-1 print:hidden">
              <Button
                size="icon"
                variant="ghost"
                aria-label="بزرگ‌نمایی"
                data-testid="viewer-zoom-in"
                onClick={() => zoomIn()}
              >
                <ZoomIn />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label="کوچک‌نمایی"
                data-testid="viewer-zoom-out"
                onClick={() => zoomOut()}
              >
                <ZoomOut />
              </Button>
              <Button
                size="icon"
                variant="ghost"
                aria-label="چرخش"
                data-testid="viewer-rotate"
                onClick={() => setRotation((r) => (r + 90) % 360)}
              >
                <RotateCw />
              </Button>
            </div>
            <TransformComponent>
              <div
                className="max-h-[70vh] overflow-hidden"
                style={{ transform: `rotate(${rotation}deg)`, transformOrigin: "center" }}
                data-testid="viewer-surface"
              >
                {pdf ? (
                  <Document
                    file={url}
                    onLoadSuccess={({ numPages }) => setPageCount(numPages)}
                    onLoadError={() => setError(true)}
                    loading="در حال بارگذاری…"
                  >
                    <Page
                      pageNumber={page}
                      width={520}
                      renderTextLayer={false}
                      renderAnnotationLayer={false}
                    />
                  </Document>
                ) : (
                  <img
                    src={url}
                    alt="رسید"
                    data-testid="viewer-image"
                    className="max-w-full"
                    onError={() => setError(true)}
                  />
                )}
              </div>
            </TransformComponent>
          </>
        )}
      </TransformWrapper>
    </div>
  );
}
