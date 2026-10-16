/** Theme tokens are measured in linear sRGB; no jsdom CSS color assumptions. */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";
import baseline from "./fixtures/dark-palette-v1.0.10.json";

const css = readFileSync(resolve(process.cwd(), "src/index.css"), "utf8");
function tokens(selector: string) {
  const block = css.split(`${selector} {`)[1].split("\n  }")[0];
  return Object.fromEntries(
    [...block.matchAll(/--([\w-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2]]),
  );
}
const light = tokens(":root");
function rgb(hsl: string): number[] {
  const [h, s, l] = hsl.match(/[\d.]+/g)!.map(Number);
  const a = (s / 100) * Math.min(l / 100, 1 - l / 100);
  return [0, 8, 4].map((offset) => {
    const k = (offset + h / 30) % 12;
    return l / 100 - a * Math.max(-1, Math.min(k - 3, 9 - k, 1));
  });
}
function contrast(a: number[], b: number[]) {
  const luminance = (channels: number[]) =>
    channels.reduce(
      (total, c, i) =>
        total +
        (c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4) * [0.2126, 0.7152, 0.0722][i],
      0,
    );
  const x = luminance(a),
    y = luminance(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
}

describe("4-B warm light surfaces", () => {
  it("uses a subtly warm cream canvas and pale green secondary surfaces", () => {
    const [r, g, b] = rgb(light.background);
    expect(r).toBeGreaterThan(g);
    expect(g).toBeGreaterThan(b);
    expect(b).toBeGreaterThan(0.9);
    expect(light.secondary).toMatch(/^90 /);
  });
  it.each(["background", "card", "muted", "secondary", "accent"])(
    "keeps normal and muted text AA on %s",
    (surface) => {
      for (const foreground of ["foreground", "muted-foreground"]) {
        expect(contrast(rgb(light[foreground]), rgb(light[surface]))).toBeGreaterThanOrEqual(4.5);
      }
    },
  );
  it.each(["primary", "destructive"])("keeps %s button text AA", (kind) => {
    expect(contrast(rgb(light[kind]), rgb(light[`${kind}-foreground`]))).toBeGreaterThanOrEqual(
      4.5,
    );
  });
  it.each(["input", "ring"])("keeps %s boundary/focus at least 3:1", (kind) => {
    for (const surface of ["background", "card"]) {
      expect(contrast(rgb(light[kind]), rgb(light[surface]))).toBeGreaterThanOrEqual(3);
    }
  });
  it.each(["positive", "negative"])("keeps semantic %s text AA", (kind) => {
    const color = rgb(light[kind]);
    for (const surface of ["background", "card", "muted"]) {
      expect(contrast(color, rgb(light[surface]))).toBeGreaterThanOrEqual(4.5);
      const tint = rgb(light[surface]).map((channel, i) => channel * 0.85 + color[i] * 0.15);
      expect(contrast(color, tint)).toBeGreaterThanOrEqual(4.5);
    }
  });
  it("does not redesign any published dark token", () => {
    expect(tokens(".dark")).toEqual(baseline.tokens);
  });
});
