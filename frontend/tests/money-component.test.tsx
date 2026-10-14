/** <Money /> — ISO code, accounting negatives, inflow/outflow colors. */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { Money } from "@/components/money";

describe("<Money />", () => {
  it("renders the ISO currency code and Persian digits", () => {
    render(<Money value="1250.5000" />);
    expect(screen.getByText("TOMAN")).toBeInTheDocument();
    expect(screen.getByText("۱٬۲۵۰.۵")).toBeInTheDocument();
  });

  it("renders accounting-style negatives as (x)", () => {
    render(<Money value="-250.0000" />);
    expect(screen.getByText("(۲۵۰)")).toBeInTheDocument();
  });

  it("can show unicode minus instead of parentheses", () => {
    render(<Money value="-250.0000" accounting={false} />);
    expect(screen.getByText("−۲۵۰")).toBeInTheDocument();
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

  it("handles null/empty as zero and hides currency on demand", () => {
    const { container } = render(<Money value={null} hideCurrency />);
    expect(container.textContent).toContain("۰");
    expect(screen.queryByText("TOMAN")).not.toBeInTheDocument();
  });
});
