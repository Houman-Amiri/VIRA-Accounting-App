/** Browser-only fallback proof; never counted as server-native PDF evidence. */
import { execFileSync } from "node:child_process";
import path from "node:path";
import { expect, test } from "@playwright/test";

test("printable fallback uses embedded Vazirmatn under its real strict CSP", async ({
  page,
}, testInfo) => {
  const root = path.resolve(process.cwd(), "..");
  const python = path.join(
    root,
    ".venv",
    process.platform === "win32" ? "Scripts/python.exe" : "bin/python",
  );
  const fixture = JSON.parse(
    execFileSync(
      python,
      [
        "-c",
        "import json; from app.services.pdf import render_html, PRINTABLE_HTML_CSP; " +
          "from scripts.pdf_native_smoke import fixture_context; " +
          "print(json.dumps(dict(html=render_html('proforma.html', fixture_context(1)), csp=PRINTABLE_HTML_CSP)))",
      ],
      { cwd: root, encoding: "utf8", env: { ...process.env, PYTHONUTF8: "1" } },
    ),
  );
  const url = "http://vira-print.test/proforma";
  const requests: string[] = [];
  const errors: string[] = [];
  page.on("request", (request) => requests.push(request.url()));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  await page.route(url, (route) =>
    route.fulfill({
      contentType: "text/html; charset=utf-8",
      headers: {
        "Content-Security-Policy": fixture.csp,
        "X-Content-Type-Options": "nosniff",
      },
      body: fixture.html,
    }),
  );
  await page.goto(url);
  await page.evaluate(() => document.fonts.ready);
  const faces = await page.evaluate(() =>
    Array.from(document.fonts).map((font) => ({
      family: font.family,
      weight: font.weight,
      status: font.status,
    })),
  );
  expect(faces).toHaveLength(2);
  expect(faces.map((font) => font.weight).sort()).toEqual(["400", "700"]);
  expect(faces.every((font) => font.family === "Vazirmatn" && font.status === "loaded")).toBe(true);
  expect(await page.locator("script").count()).toBe(0);
  expect(requests).toEqual([url]);
  expect(errors).toEqual([]);

  // Actual platform fonts used for the normal and bold 30-digit probes, not
  // merely computed CSS or a FontFaceSet entry that might still fall back.
  const session = await page.context().newCDPSession(page);
  await session.send("DOM.enable");
  await session.send("CSS.enable");
  const { root: document } = await session.send("DOM.getDocument");
  const proof = [];
  for (const [selector, expected] of [
    [".muted", "Vazirmatn-Regular"],
    [".grand .num", "Vazirmatn-Bold"],
  ]) {
    const { nodeId } = await session.send("DOM.querySelector", {
      nodeId: document.nodeId,
      selector,
    });
    const { fonts } = await session.send("CSS.getPlatformFontsForNode", {
      nodeId,
    });
    expect(fonts.length).toBeGreaterThan(0);
    expect(fonts.every((font) => font.isCustomFont && font.postScriptName === expected)).toBe(true);
    proof.push({ selector, fonts });
  }
  await testInfo.attach("printable-font-proof", {
    body: JSON.stringify({ faces, proof, requests, errors }, null, 2),
    contentType: "application/json",
  });
});
