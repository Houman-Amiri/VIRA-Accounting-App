/** <Money /> — unit policy (Rial→Toman ÷10 once), accounting negatives, colors. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Money } from "@/components/money";

describe("<Money />", () => {
  it("renders stored Rials as Tomans (÷10 exactly once) with Persian digits", () => {
    render(<Money value="1250.5000" />);
    expect(screen.getByText("تومان")).toBeInTheDocument();
    // 1 250.5000 Rial = 125.05 Toman
    expect(screen.getByText("۱۲۵.۰۵")).toBeInTheDocument();
  });

  it("can show the source Rial amount", () => {
    render(<Money value="1250.5000" display="source" />);
    expect(screen.getByText("ریال")).toBeInTheDocument();
    expect(screen.getByText("۱٬۲۵۰.۵")).toBeInTheDocument();
  });

  it("renders Toman-native values unchanged (price calculator)", () => {
    render(<Money value="421712.3875" currency="TOMAN" />);
    expect(screen.getByText("تومان")).toBeInTheDocument();
    expect(screen.getByText("۴۲۱٬۷۱۲.۳۸۷۵")).toBeInTheDocument();
  });

  it("renders foreign currencies as-is with the ISO code", () => {
    render(<Money value="10.0000" currency="EUR" />);
    expect(screen.getByText("EUR")).toBeInTheDocument();
    expect(screen.getByText("۱۰")).toBeInTheDocument();
  });

  it("renders accounting-style negatives as (x)", () => {
    render(<Money value="-250.0000" />);
    // -250 Rial = -25 Toman
    expect(screen.getByText("(۲۵)")).toBeInTheDocument();
  });

  it("can show unicode minus instead of parentheses", () => {
    render(<Money value="-250.0000" accounting={false} />);
    expect(screen.getByText("−۲۵")).toBeInTheDocument();
  });

  it("applies inflow/outflow colors on demand", () => {
    const { container } = render(<Money value="10.0000" signedColors />);
    expect(container.querySelector(".text-positive")).not.toBeNull();
    const neg = render(<Money value="-10.0000" signedColors />);
    expect(neg.container.querySelector(".text-negative")).not.toBeNull();
  });

  it("honors a forced direction (e.g. debit = outflow)", () => {
    const { container } = render(<Money value="10.0000" direction="outflow" />);
    expect(container.querySelector(".text-negative")).not.toBeNull();
  });

  it("keeps figures LTR-isolated inside RTL pages", () => {
    const { container } = render(<Money value="1.2345" />);
    const span = container.querySelector(".num");
    expect(span?.getAttribute("dir")).toBe("ltr");
  });

  it("handles null/empty as zero and hides the unit label on demand", () => {
    const { container } = render(<Money value={null} hideCurrency />);
    expect(container.textContent).toContain("۰");
    expect(screen.queryByText("تومان")).not.toBeInTheDocument();
  });
});
