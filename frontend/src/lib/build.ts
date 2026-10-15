/**
 * Build identity of the UI that is *actually running in this browser*.
 *
 * The id is stamped into `index.html` («vira-build») by vite.config.ts and read
 * back from the DOM here — that makes it the id of the loaded bundle, not of
 * the source tree. «سیستم و عملیات» shows it next to the installation's id
 * (`spa_build`), so a stale cached UI reports itself instead of hiding new
 * screens (v1.0.5 incident).
 */
export const UI_BUILD_ID: string =
  typeof document === "undefined"
    ? "unknown"
    : (document.querySelector('meta[name="vira-build"]')?.getAttribute("content") ?? "unknown");

/** Build id baked in at compile time (secondary source, e.g. for headers). */
export const COMPILED_BUILD_ID: string =
  typeof __VIRA_BUILD_ID__ === "undefined" ? UI_BUILD_ID : __VIRA_BUILD_ID__;

/** True when the loaded bundle does not match what the installation ships. */
export function isStaleUi(installedBuild: string | null | undefined): boolean {
  if (!installedBuild || UI_BUILD_ID === "unknown" || COMPILED_BUILD_ID !== UI_BUILD_ID)
    return false;
  return installedBuild !== UI_BUILD_ID;
}
