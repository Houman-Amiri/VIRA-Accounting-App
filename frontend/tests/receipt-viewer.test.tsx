/** Phase 7 §2 — <ReceiptViewer /> faceted viewer: image facet + PDF page nav. */
import * as React from "react";
import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

vi.mock("react-pdf", () => ({
  Document: ({
    children,
    onLoadSuccess,
  }: {
    children: React.ReactNode;
    onLoadSuccess: (info: { numPages: number }) => void;
  }) => {
    React.useEffect(() => {
      onLoadSuccess({ numPages: 3 });
    }, [onLoadSuccess]);
    return <div data-testid="pdf-doc">{children}</div>;
  },
  Page: ({ pageNumber }: { pageNumber: number }) => (
    <div data-testid="pdf-page">page-{pageNumber}</div>
  ),
  pdfjs: { GlobalWorkerOptions: { workerSrc: "" } },
}));

import { ReceiptViewer } from "@/components/receipt-viewer";

describe("ReceiptViewer", () => {
  it("renders the image facet with zoom/rotate controls", async () => {
    render(<ReceiptViewer url="/api/v1/documents/receipts/abc" mediaType="image/png" />);
    expect(screen.getByTestId("viewer-image")).toBeTruthy();
    expect(screen.getByTestId("viewer-zoom-in")).toBeTruthy();
    expect(screen.getByTestId("viewer-rotate")).toBeTruthy();
    // image facet has no page flips
    expect(screen.queryByTestId("viewer-next")).toBeNull();
  });

  it("PDF facet exposes faceted page navigation (_prev/_next)", async () => {
    render(<ReceiptViewer url="/api/v1/documents/receipts/xyz.pdf" mediaType="application/pdf" />);
    await waitFor(() => expect(screen.getByTestId("pdf-doc")).toBeTruthy());
    // 3 pages loaded → next enabled, prev disabled at page 1
    const next = screen.getByTestId("viewer-next") as HTMLButtonElement;
    const prev = screen.getByTestId("viewer-prev") as HTMLButtonElement;
    await waitFor(() => expect(next.disabled).toBe(false));
    expect(prev.disabled).toBe(true);
    expect(screen.getByTestId("viewer-page").textContent).toContain("1");
    fireEvent.click(next);
    expect(screen.getByTestId("viewer-page").textContent).toContain("2");
    fireEvent.click(next);
    expect(screen.getByTestId("viewer-page").textContent).toContain("3");
    expect((screen.getByTestId("viewer-next") as HTMLButtonElement).disabled).toBe(true);
  });
});
