import { afterEach, describe, expect, it } from "vitest";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { StepGuide } from "@/components/guide-steps";

afterEach(() => {
  cleanup();
  window.localStorage.clear();
});

const steps = [
  { title: "گام یک", body: "توضیح یک" },
  { title: "گام دو", body: "توضیح دو" },
];

describe("in-app step guide (item 9)", () => {
  it("lists the numbered steps and a short intro", () => {
    render(<StepGuide id="t1" title="راهنما" intro="مقدمه" steps={steps} />);
    expect(screen.getByTestId("guide-t1")).toBeInTheDocument();
    expect(screen.getByText("مقدمه")).toBeInTheDocument();
    const items = within(screen.getByTestId("guide-t1-steps")).getAllByRole("listitem");
    expect(items).toHaveLength(2);
    expect(items[0]).toHaveTextContent("گام یک");
    expect(items[1]).toHaveTextContent("گام دو");
  });

  it("collapses the list without losing the title", () => {
    render(<StepGuide id="t2" title="راهنما" steps={steps} />);
    fireEvent.click(screen.getByTestId("guide-t2-toggle"));
    expect(screen.queryByTestId("guide-t2-steps")).not.toBeInTheDocument();
    expect(screen.getByText("راهنما")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("guide-t2-toggle"));
    expect(screen.getByTestId("guide-t2-steps")).toBeInTheDocument();
  });

  it("stays dismissed after a reload and can be reopened", () => {
    const first = render(<StepGuide id="t3" title="راهنما" steps={steps} />);
    fireEvent.click(screen.getByTestId("guide-t3-dismiss"));
    expect(screen.queryByTestId("guide-t3")).not.toBeInTheDocument();
    expect(window.localStorage.getItem("vira-guide-dismissed:t3")).toBe("1");
    first.unmount();

    render(<StepGuide id="t3" title="راهنما" steps={steps} />);
    expect(screen.queryByTestId("guide-t3")).not.toBeInTheDocument();
    fireEvent.click(screen.getByTestId("guide-t3-reopen"));
    expect(screen.getByTestId("guide-t3")).toBeInTheDocument();
    expect(window.localStorage.getItem("vira-guide-dismissed:t3")).toBeNull();
  });

  it("keeps each page's guide independent", () => {
    render(
      <>
        <StepGuide id="a" title="الف" steps={steps} />
        <StepGuide id="b" title="ب" steps={steps} />
      </>,
    );
    fireEvent.click(screen.getByTestId("guide-a-dismiss"));
    expect(screen.queryByTestId("guide-a")).not.toBeInTheDocument();
    expect(screen.getByTestId("guide-b")).toBeInTheDocument();
  });
});
