import { afterEach, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { LoginPage } from "@/routes/login";

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock("react-i18next", async () => {
  const fa = (await import("@/locales/fa/common.json")).default as Record<
    string,
    Record<string, string>
  >;
  return {
    useTranslation: () => ({
      t: (key: string) => {
        const [group, name] = key.split(".");
        return fa[group]?.[name] ?? key;
      },
    }),
  };
});

afterEach(cleanup);

it("shows the NOA mark instead of the placeholder tile", () => {
  render(<LoginPage />);
  const logo = screen.getByTestId("login-logo");
  expect(logo).toHaveAttribute("src", "/noa-icon-192.png");
  expect(screen.queryByText("و")).toBeNull();
});

it("tells the owner where the password lives when it is forgotten", () => {
  render(<LoginPage />);
  const hint = screen.getByTestId("login-forgot");
  // the file is the recovery path, so its exact location must be on screen
  expect(hint).toHaveTextContent("owner-password.txt");
  expect(hint).toHaveTextContent("%LOCALAPPDATA%");
  // ... and the lockout has an instruction that actually works
  expect(screen.getByText(/تعداد تلاش بیش از حد/)).toBeInTheDocument();
});
