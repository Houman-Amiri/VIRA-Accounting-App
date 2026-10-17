/** User amendment: numbers use Vazirmatn, not a separate monospace family. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { expect, it } from "vitest";
import config from "../tailwind.config";

const source = (name: string) => readFileSync(resolve(process.cwd(), name), "utf8");
it("uses the shared Vazirmatn family for numeric and legacy utility styles", () => {
  const family = config.theme.extend.fontFamily;
  expect(family.sans[0]).toBe("Vazirmatn Variable");
  expect(family.mono).toEqual(family.sans);
  const numericRule = source("src/index.css").match(/\.num\s*\{([^}]+)\}/)![1];
  expect(numericRule).toContain("@apply font-sans tabular-nums");
  expect(numericRule).toContain("direction: ltr");
  expect(numericRule).toContain("unicode-bidi: isolate");
});
it("does not load or force JetBrains Mono in the application", () => {
  expect(source("src/main.tsx")).not.toMatch(/jetbrains/i);
  expect(source("src/routes/system.tsx")).not.toContain("font-mono");
  expect(JSON.parse(source("package.json")).dependencies).not.toHaveProperty(
    "@fontsource/jetbrains-mono",
  );
});

it("keeps the trial chart on the shared font-aware renderer and typed list response", () => {
  const statements = source("src/routes/statements.tsx");
  expect(statements).toContain("<EChart");
  expect(statements).not.toContain("echarts.init");
  expect(statements).not.toContain("as unknown");
  expect(statements).not.toContain("trial.data?.rows");
});
