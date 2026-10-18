# Changelog

All notable changes to V.I.R.A are documented here. Versions follow strict
SemVer `MAJOR.MINOR.PATCH`; every released version has an immutable annotated
git tag `vX.Y.Z`. Releases are published on GitHub Releases with the Inno Setup
installer, delta packages, `latest.json`, `SHA256SUMS` and Persian notes.

## [Unreleased]

### Independent native PDF rebuild preparation and CRT evidence
- Add an isolated PowerShell 7 native-only build entry point and native inspector,
  explicit MIT derivatives within the 11-file allowlist. Compile from the licensed
  sidecar, fresh absolute work directory and pinned vcpkg without application,
  Node/uv/app Python/staging dependencies; clear binary caches and permit overlays.
- Record actual original MSVC 19.51 / VS18-v145 / SDK 26100 compiler logs, installed
  English terms and official 2026 VS/Build Tools/C++ Runtime agreements. Keep
  entitlement/static-CRT mapping pending; installation/REDIST is not legal approval.
- Independent Windows rebuild 39108011284 / d5b2516 succeeds: 20 original
  preferred-source trees and 21 DLL owners/PE closure/private loaded origins
  verified; two complete metadata chunks committed, no binary upload. Track
  ordinary regression in
  `docs/dependencies/pdf-native-rebuild-proof-run.json`; do not equate plan tests
  with completed compilation or native loading with app/installed acceptance.
- Preserve Windows readiness/rollback failure evidence; make test-harness failure
  annotations Unicode/code-page safe without weakening readiness or hashes. Add
  exact-CRLF/cp1252 regression coverage; 476 backend tests, 71 focused checks,
  Ruff/Mypy/Bandit pass locally. All five ordinary CI jobs 39110216955 / 867dfd3
  pass, including Windows real delta/schema/compiled-helper rollback, 196 frontend
  tests and six browser scenarios. Preserve the original unexplained readiness
  failure and intermediate test/lint failures rather than claiming a proven
  production root-cause fix from a successful retry.
- No native payload integration, release/tag/version, broad license, user-data or
  pricing changes; source delivery and all remaining production gates stay open.


### Owner-approved MIT grant for native PDF build files only
- Record explicit owner consent (2026-10-18) and the full MIT text for nine listed
  native PDF build/configuration/documentation/checker files. Exact reference
  hashes and seven original-archive member bindings prevent an accidental
  repository-wide grant; application/backend/frontend/installer and third-party
  library/CRT code are NOT relicensed.
- Add a standard-library scope checker and limited source/license sidecar builder:
  preserve UTF-8, allow checkout CRLF/LF only, reject widened scope, changed source,
  substituted license, symlinks and overwriting existing sidecar data. Attach the
  grant and licensed sources to the private source-review artifact, not a release.
- 24 new scope/sidecar tests, 57 focused checks and 462 backend tests pass locally;
  Ruff/Mypy (84 app files) and configured Bandit checks pass. All five ordinary CI
  jobs (39104212641 / 0742355) and scoped-source/sidecar audit 39104212604 pass,
  with 196 frontend / six browser scenarios and Windows rollback. The recipe-rights
  substep is recorded, but full workflow completeness, CRT/library obligations,
  recipient delivery and production runtime/update gates remain open. No native
  recompilation, version/tag/release, application/data/math change or installed
  user acceptance is inferred.

### Prepared native PDF license/source-delivery materials (not legal approval)
- Bind proposed license selections for all 20 source packages / 21 DLLs to the
  immutable source inventory. Generate complete original notices plus 11 actual
  source supplements, verified against the original patched source ZIP; recover
  all 19 supplemental metadata chunks without recompiling native code.
- Fix incomplete PCRE2 COPYING evidence: preserve the actual BSD-3-Clause WITH
  PCRE2-exception license and separately pinned SLJIT BSD-2-Clause notice. Propose
  FTL for FreeType with attribution and nine contributed-code notices; distinguish
  LGPL libiconv libraries from GPL CLI/docs, without inventing missing port SPDX.
- Real Windows CI caught legacy-codepage copyright corruption; explicit UTF-8
  reads and LF JSON writes fix it without weakening hashes. 438 backend tests,
  including 25 new license tests, and 33 focused checks pass; Ruff/Mypy/Bandit pass.
  All five ordinary CI jobs (39102792071 / 40addf7) and the independent license
  source audit (39102792100) pass; 196 frontend / six browser scenarios.
- Preserve the source/review copy for 90 days, not a public source-delivery claim.
  Specify same-release source/recipe/notices access and expose missing transitive
  wrapper dependencies. Component legal/CRT/recipe rights, LGPL replacement and
  real recipient delivery remain hard gates; no MIT grant for VIRA, native runtime
  integration, public release/tag/version bump or user-data/math changes.
  See `docs/reports/pdf-runtime-license-materials-fa.md`.

### Verified pinned-source PDF runtime proof (not distribution approval)
- Build 35 native/host packages from an immutable vcpkg source baseline, with
  native binary caches disabled. NEW private candidate: 21 DLLs / 14,417,408 bytes;
  all load from the relocated staged production CPython 3.11.17 payload. The old
  27 SDK DLLs remain UNREVIEWED, not approved by this different source build.
- Capture 20 target packages / 25,505 source entries / 21 bounded symlinks, complete
  recipes/patches/build wrappers, installed ownership, SPDX, copyright texts and
  hashes. Independently verify the actual source ZIP and PDF evidence, recovering
  all 47 metadata chunks despite GitHub's per-step notice cap; no native rebuild.
- Real source-build tests exposed/fixed a static-CRT gettext host-tool crash and
  source-symlink capture failure. Host tools now use a separate dynamic-CRT release
  triplet and never enter the candidate. Target source symlinks are retained safely;
  absolute/escaping links and missing native sources/notices remain failures.
- 413 backend / 196 frontend / six browser scenarios pass; all five ordinary CI
  jobs on `b6c5475` (39052300805), native source run 39048889428 (`2ec79b8`) and
  independent evidence audit 39052300861 pass. Same one/four-page PDF hashes,
  actual Vazirmatn 400/700 embedding and all 30 used digits in both weights.
- Candidate remains DO_NOT_DISTRIBUTE. License choices (including libiconv's missing
  port license declaration), compiler/CRT/recipe rights, durable source delivery,
  Unicode bootstrap, normal native update/rollback and installed-user acceptance
  remain open. No native binary upload, public release/version or data/math changes.
  See `docs/reports/pdf-runtime-source-build-fa.md` and the full source inventories.

### Private bundled-Python PDF audit (not a distributable runtime)
- Audit the hash-pinned upstream runtime's x64 PE import/delay-import closure:
  27 DLLs / 15,534,142 bytes, excluding 51 unrelated upstream DLLs. Preserve hashes,
  imports and version-resource evidence in `docs/dependencies/` without binaries.
- Actual production staging now explicitly selects managed, non-venv CPython and
  checks native command failures. A relocated private staged CPython 3.11.17
  payload renders the same one/four-page embedded-Vazirmatn PDFs under `-I`,
  without dev inspection packages. All 27 audited DLLs load from the candidate.
- The new gate caught a real libffi basename collision and Fontconfig Unicode
  environment-path loss. Private early libffi preload + ctypes callback tests
  and an ASCII temporary Fontconfig path pass; general startup/Unicode support
  is NOT yet a production feature. All libraries remain license/source UNREVIEWED.
- 387 backend / 196 frontend / six CI browser scenarios pass; all five CI jobs
  succeed on `d848a08` (39038459962), including old migration/update rollback gates.
  No native binaries added to release payloads or uploaded as artifacts; no release.
  See `docs/reports/pdf-runtime-payload-audit-fa.md` for remaining gates.

### Verified native PDF/font proof (unpublished; runtime packaging still open)
- Printable HTML fallback now embeds both self-hosted Vazirmatn fonts instead
  of broken API-relative font paths. PDF resource fetching is restricted to the
  two bundled TTFs; business values and fallback content types are unchanged.
- Strict Windows native proof inspects real PDF text operators, embedded font
  bytes/weights and used Unicode digits, including multipage A4 documents.
  A SHA-pinned official WeasyPrint runtime is a CI-only fixture, NOT yet a
  distributable install/delta runtime. Legal/source and installed-payload gates
  remain open. Fallback-only CSP permits embedded fonts while keeping scripts
  and external resources blocked. The fetcher uses the already-locked WeasyPrint
  70 API (no engine upgrade) and normalizes fatal font-resource errors to fallback.
- 368 backend / 196 frontend tests and six real-browser scenarios pass. All five
  CI jobs pass on `e5e3364` (38996175479), including strict native Windows PDF/API
  proof, real delta rollback and public-1.0.10 schema/data rollback. Native PDFs:
  one and four A4 pages; embedded Regular/Bold with all 30 used digits in each.
  See `docs/reports/native-pdf-font-proof-fa.md`.

### Added — repair substep 4-B/3-B (unpublished)
- Settings manages persisted item types, units and the existing shared supplier
  registry. New item consumes active server options; inactive labels remain in
  historical inventory, alarms and dashboards. Unused custom choices may be
  deleted with confirmation; used/default choices deactivate and can reactivate.
- `0006_item_catalog` preserves all inventory columns and inbound references via
  a checked, atomic SQLite table rebuild; runtime foreign keys remain enabled.
  Migration failures roll back DDL, data and revision together; lossy downgrades
  refuse and require the verified pre-upgrade snapshot.
- New types mean general stock, never implicit filament/products. Canonical
  production units remain explicit; no quantity/unit/price/history conversion.
  Catalog changes require write roles, CSRF and matching revisions and are audited.
- Derived inventory values accept the full eight decimal places of two scaled-four
  inputs instead of failing response validation or rounding away exact values.
- Inventory indexes/triggers, including local additions, survive the rebuild;
  empty/missing supplier references are rejected before SQL constraint failures.
- Local: 357 backend / 196 frontend tests; five real-browser scenarios including
  catalog lifecycle, mobile/desktop, both themes and unchanged workbook pricing.
  All five CI jobs passed on `fb82b2c` (run 38992081789), including final catalog
  DDL from public 1.0.10 and compiled-helper database rollback. No release/tag.

### Changed — shared numeric typography (unpublished)
- User amendment: Vazirmatn now covers numbers as well as text, including shared
  numeric styles, native form controls, technical/version values, chart labels
  and tooltips. Removed the separate JetBrains font dependency; legacy monospace
  utilities resolve to the shared Vazirmatn stack.
- Trial-balance chart uses the shared font-aware renderer and the actual typed
  list API response, fixing its previously empty rows/chart without changing
  stored or calculated amounts.
- Proforma numeric styles use bundled OFL Vazirmatn Regular/Bold (v33.003), covering
  Latin, Persian and Arabic digits offline. Native PDF rendering/installed Windows
  visual acceptance remains separate from HTML/font-asset verification.
- 338 backend / 189 frontend tests and all five browser scenarios passed locally;
  all five CI jobs passed for `9fda819` (run 38988854225), including Windows native
  delta apply and real-schema rollback. No schema, stored number, arithmetic,
  numeral system or release/version change.

### Changed — repair substep 4-B/1 (unpublished)
- Pricing report now exposes only description/plain/chain amounts, without cell
  references or formula annotations. Literal workbook math and all three colored
  total rows remain unchanged.
- Warm cream light canvas, pale-green secondary surfaces, AA text/semantic colors
  and stronger input borders; published dark tokens remain unchanged. Compact,
  accessible mobile navigation retains the startup update notification; normal
  three-column amounts fit, oversized amounts scroll inside the report.
- 158 frontend tests and five CI jobs passed on `b45e18e` (run 38969506200).
  No backend/schema/migration or release/version change. Calendar and dynamic
  item master data were still pending at that checkpoint; installed manual acceptance is deferred by
  the user's instruction until the phases finish.

### Changed — repair substep 4-B/2 (unpublished)
- Real Jalali/Gregorian civil-date inputs for orders/new journals, shared date
  filters, lists and entry previews. Persian/Arabic/Latin digit input, validity
  checks and Tehran today; ISO date-only storage and UTC timestamps are unchanged.
- Settings calendar selection is installation-wide, durable in existing SQLite
  append-only events, authenticated/CSRF-protected and revision-checked. No DDL or
  new migration; invalid/corrupt preference fails closed for date entry.
- Calendar switching preserves the civil day, including an edited unsaved date;
  fiscal boundaries stay on 1 Farvardin. Journal auth-recovery drafts retain date.
- Responsive date forms and internally scrolling order tables keep mobile inputs
  readable. Light/dark tokens and literal pricing formulas remain unchanged.
- Local checks: 326 backend tests, 186 frontend tests and all five browser journeys
  passed; browser calendar coverage uses real SQLite, two browser timezones,
  frozen Tehran-midnight clock, reload and a fresh authenticated browser context.
  All five CI jobs passed on `1defaad` (run 38981489594), including native Windows
  and the OpenAPI contract. Evidence/limits: `docs/reports/phase4b-2-calendar-fa.md`.
- No version/tag/publication or installed-user database changes. Dynamic item
  master data and its schema-rollback prerequisite remain pending.

### Fixed — repair substep 4-B/3 safety prerequisite (unpublished)
- Updater rollback now has a hash-verified standalone SQLite snapshot/restore tool
  for the exact attempt, including schema and all data after a target migration.
  Failed-target DB/WAL files are retained; unchanged DBs are not rewritten.
- Block HTTP mutations and recurring jobs in current code during verified apply;
  target writes must not be acknowledged before a potential rollback.
- Add a Windows CI gate using the immutable public 1.0.10 client, compiled helper,
  a real test-only Alembic revision, forced post-migration failure and original
  schema/data/readiness checks. Evidence/status: `docs/reports/phase4b-3a-schema-rollback-fa.md`.
- All five CI jobs passed on `1a3bdf5` (run 38985887353), including the public
  1.0.10 compiled-helper schema rollback probe. Local 335 backend / 186 frontend
  tests passed. No production schema revision,
  catalog Settings UI, version/tag/publication or installed-data changes in this
  checkpoint; the actual catalog migration and its exact rollback gate remain open.

## [1.0.10] - 2026-10-16

Reviewed Persian notes: `docs/releases/v1.0.10-fa.md`. The user approved tagging
and public release after the green candidate report. Publication is gated by
CI and the Windows/historical-client checks on the immutable release tag.
The confirmed installed baseline is v1.0.9 / `7d78720`; its browser-to-candidate
success and rollback gate passed on `f6fc50b` before approval.

### Fixed
- Add a pinned-public-payload 1.0.9 -> candidate 1.0.10 browser/compiled-updater
  pre-release gate (no injected bootstrap or modified historical client). Recover
  the durable result path from the historical staging layout when the old client
  omits the new helper argument. Bridge a restarted idle manager with the active
  helper lock until that exact attempt (nonce + PID) has a terminal result, so
  the historical UI keeps polling during readiness checks. All six tagless-release
  jobs passed on candidate `f6fc50b` (run 38956957333), including the unchanged
  published browser, finish button, explicit reload and success/rollback data
  checks. Publication was skipped; installed-user acceptance remains open.
- Repair phase 8: bind download consent to the exact version/hash, reject automatic
  full-setup fallback, retain sudo/owner protection for mutations, verify restart
  health/build identity and file rollback, persist the terminal update result and
  reload the UI only after verified success. Real current-source Windows browser
  journeys cover success/rollback and unchanged SQLite/receipt hashes; these do
  not by themselves prove the historical v1.0.9 client's first update or installed-user acceptance.
- Repair phase 7: select actual order lines in production, preserve stored prices,
  validate remaining quantities and inventory links, and atomically consume
  filament/add finished stock without duplicate completion. Add complete list
  pagination, precise Persian numeric input and actionable domain errors.
  Proforma may fall back to printable HTML; native Windows PDF and Word export
  are not claimed. No new migration or historical-price rewrite.

- Repair phase 6: real-data dashboard with six KPIs, four Toman-unit plots and
  exact accessible source tables, actionable inventory/supplier, accounting,
  production and pending-order alerts. Use Tehran's civil day, explicit as-of/YTD
  windows and a continuous 30-day sales axis. Loading/errors never look like
  healthy zeroes; failed refreshes hide stale figures and offer retry.
- Remove floating-point report aggregation, double-counted trial-balance parents
  and the inverted retained-earnings expense sign. Preserve the fifth Toman
  decimal when displaying four-decimal Rials. Cash uses 101/102 account prefixes,
  not inventory/receivables; operational money is already Toman and not divided.
- Add read-only, role-protected order counts independent of the recent page;
  remove the hidden 10,000-record sales/production-summary cap and prioritize
  active production jobs in the sample. Inventory totals include all active items,
  not just the first 500. Charts follow container size and theme.
  No new migration, stored-price rewrite, version/tag or public release.
  See `docs/reports/phase6-dashboard-fa.md`; phase 4-B remains queued.
- Repair phase 5: explicitly theme selected/disabled native options, disabled
  groups and keyboard focus; respect OS forced-colors. Palette items no longer
  inherit muted group-heading text, and Escape works while its input is focused.
- Keep the selected light/dark theme across reloads with a validated local
  preference; blocked/full storage does not prevent in-session theme changes.
  Browser tests audit 24 real native controls per theme plus palette navigation,
  live search, disabled-state fixtures and high contrast. No pricing/date/catalog
  changes, migrations or new public release in this phase.

### Planned (not implemented)
- Repair subphase 4-B: remove visible pricing cell references; add persistent
  Jalali/Gregorian calendar selection with Tehran-based today and actual calendar
  input in orders/journal entry; manage item types, units and suppliers in settings;
  subtly tint the light theme. Scope and acceptance criteria live in
  `docs/plans/pricing-dates-catalog-theme-follow-up-fa.md`. The newly requested
  calendar switch supersedes the older Jalali-only restriction in both specs.

## [1.0.9] — 2026-10-16

### Changed
- Remove the Excel explanation banners from pricing and move constant editing to
  Settings → Pricing constants. Save seven active constants in SQLite (scaled
  integer Rials; exact Toman API strings), with validation, CSRF, role checks,
  revision conflict protection and an audit event. New calculations in pricing,
  orders and production share the saved values; existing prices are untouched.
  Resetting product inputs no longer resets saved preferences. Migration
  `0005_pricing_settings` adds only the settings table with the existing defaults.
- Pricing report highlights the entire B25/E25 row in green, B29/E29 in blue,
  and B35/E35 in red, with readable light/dark backgrounds. Workbook formulas,
  displayed amounts and the derived batch-price row are unchanged.

### Fixed
- Release smoke checks the exact SHA-256 of installed JavaScript against the
  built payload, not a DOM test id composed only at runtime. Browser tests
  continue to check the rendered pricing row ids and highlight colors.

## [1.0.8] — 2026-10-16

### Fixed
- Update dialog no longer stays at cached `idle` / zero bytes: mutation results
  replace stale status, and polling runs while requests or server work are active.
  Persian API/network errors and log paths are visible without claiming rollback.
- Download jobs return an initial status before streaming in the background;
  isolated, size-bounded `.part` files are hash-checked and safely extracted before
  staging. Only a direct delta is accepted; no full-Setup update fallback.
- Applying a verified delta now requires a verified WAL-aware SQLite backup before
  launching the helper. These changes do not establish a real Windows in-app
  upgrade; older installations require a manual delta bootstrap. See
  `docs/reports/update-zero-bytes-fa.md` for regression evidence and open gates.

## [1.0.7] — 2026-10-15

### Fixed
- **Literal pricing-workbook parity (repair phase 4, user-selected policy).**
  Previous tests repeated the application's normalized assumptions instead of
  validating the XLSX. Preserve B25/E25 quantity behavior, share B31 commission
  and the plain B34×10% buffer across variants, and leave B2/B7/B8 unused.
  The real cached sample is B35=2760748.5 and **E35=2780748.5 Toman**, not
  E35=2785630.5. A stdlib-only extractor verifies all formulas and cached values,
  pins the workbook SHA-256 and generates seven independent regression cases.
- Pricing table now shows correct B/E cell references, the actual B32 row and
  clearly marked derived values; reset restores constants as well as inputs.
  Orders/jobs use the same engine and derive unit-cost snapshots from the
  authored production total divided by quantity; existing saved prices remain
  untouched. Installed-client verification remains pending in repair phase 4.

## [1.0.6] — 2026-10-15

Makes a release *provable*: v1.0.5 installed the new code but a browser could keep
running the previous UI, and nothing in the pipeline noticed.

### Fixed
- **A successful upgrade could still show the previous UI.** v1.0.5 installed the
  new code and the new bundles, yet the browser kept running the *old* one — the
  SPA shell (`index.html`) was served without any `Cache-Control`, and the
  installer left the previous hashed bundles next to the new ones in
  `{app}\static`, so a cached shell kept loading the old bundle. Users saw
  «none of the changes applied».

  - `app/main.py` — the SPA is now served by an explicit shell route: the shell
    is `Cache-Control: no-store, must-revalidate` and never answers `304`
    (a conditional hit would hand the browser its stale copy back), hashed
    assets under `/assets/` are `immutable`, unknown non-API paths fall back to
    the shell (so `/warehouse` deep links work), unknown `/api/**` paths stay
    JSON 404s, and every shell response carries `X-VIRA-SPA-Build` with the
    build id the installation ships.
  - `installer/vira.iss` — `[InstallDelete]` removes `{app}\static`,
    `{app}\app` and `{app}\backend` before copying the new payload, and the
    installer stops any running instance inside `{app}` first (a live
    interpreter locks `python.exe`/`.pyd`, which previously forced Inno to ask
    for a reboot while leaving the old files in place).
  - **Build identity is now visible**: vite stamps `<meta name="vira-build">`
    into `index.html`, `stage_app_payload.ps1` records it as `spa_build` in
    `version.json`, and «سیستم و عملیات» shows the installed id next to the id
    the browser actually loaded — with an explicit warning to press `Ctrl+F5`
    when they differ. A stale UI can no longer hide.
  - `app/version.py` — `spa_build` joined `version_info()`, and the `VIRA_*`
    environment overrides are no longer frozen by the `lru_cache` (that cache is
    what kept an install reporting `0.0.0-unknown` after its stamp was fixed).
  - CI now proves the content: the Windows smoke test compares the build id of
    the *served* shell with the payload this run built, greps the served bundle
    for the new screens' markers (`chart-stock`, `job-submit`, `order-submit`,
    `movement-submit`, `dashboard-alerts`), asserts the operations API is present
    in the installed backend, and asserts the shell is `no-store`. A stale
    install can no longer be published silently.
  - `backend/tests/test_spa_serving.py` — 6 regression tests for the above.

## [1.0.5] — 2026-10-15

Closes the five defects reported after v1.0.4: fake version stamp, wrong
pricing-sheet interface, unreadable dark-mode dropdowns, a bare dashboard and
the missing warehouse/production modules.

### Fixed
- **«سیستم و عملیات» showed `0.0.0-unknown`.** `app/version.py` now resolves
  the version/commit with a real precedence chain — `VIRA_VERSION` /
  `VIRA_GIT_COMMIT` / `VIRA_BUILT_AT` env → the shipped `version.json` (looked up
  next to the interpreter, in `VIRA_APP_DIR`, the repo root and the cwd) →
  `importlib.metadata` → `git rev-parse --short HEAD` → `0.0.0-unknown` as a
  last resort. `stage_app_payload.ps1` stamps `commit`/`built_at` into
  `version.json` and `start_vira.cmd` exports the env pair, so an installed app
  always reports a concrete version and commit.
- **Pricing-tab formulas did not match `قیمت نهایی.xlsx`.** `lib/priceCalc.ts`
  is now a cell-exact transcription of the sheet (B3–B35 / E25 / E35) with the
  sheet's own quirks preserved as opt-in switches and Persian/Arabic digit input
  parsing. The page is a two-column B/E interface that mirrors the workbook
  row-for-row (240 g / 10 h / 1 pc → 2,760,748.5 تومان, E35 2,785,630.5 تومان).
- **Dark-mode dropdowns were unreadable** (white text on the white OS popup):
  `color-scheme: light|dark`, `select`/`option`/`optgroup` now inherit the card
  surface, and the four `bg-transparent` selects were dropped.

### Fixed
- **«بررسی به‌روزرسانی» crashed with HTTP 500 on unstamped installs.** v1.0.4
  reported its version as `0.0.0-unknown` (no distribution metadata in the
  installed payload), and `check_for_update` fed that straight into
  `SemVer.parse`, raising `SemVerError` before any comparison — the user saw a
  generic error and a traceback in the launcher console. The check now parses
  the running version defensively: an unparseable/absent version is treated as
  "no comparable base", so the app answers 200 with `manual_required: true`, a
  Persian explanation and the full-installer package (POST
  `/system/update/download` refuses to stage it, by design). A manifest whose
  own `version` is not strict SemVer is refused with the Persian reason instead
  of raising, and `fetchUpdateCheck` now surfaces the server's RFC 9457 detail
  rather than a bare «check failed». «سیستم و عملیات» shows the manual step and
  a direct «دانلود فایل نصب کامل» link. Regression tests:
  `test_unstamped_current_never_raises`,
  `test_unparseable_manifest_version_refused`,
  `test_check_updates_with_unstamped_version_is_not_a_500`.
- **`VIRA_APP_DIR` is exported by `start_vira.cmd`** so `version.json` is found
  in the installed layout even when a system Python (not the bundled one) ends
  up running the backend.

- **The update could never apply itself: the helper was never in the install.**
  `vira-updater.exe` was compiled *after* both the Inno setup and the app
  payload zip, so `{app}\vira-updater.exe` did not exist in an installed app;
  `launch_updater` only checked the staging directory and a wrong fallback
  (`%LOCALAPPDATA%\vira-updater.exe`). The helper is now compiled *before* the
  packaging steps, so it ships inside the setup, inside `vira-<v>-app.zip`
  (delta base) and inside every delta; the app resolves it as
  staging → `{app}` → data directory → `scripts\vira_updater.ps1` through
  `powershell.exe`. It always passes the installation directory explicitly
  (`-install-dir`), so a hand-unzipped or portable install no longer needs the
  installer's registry record, and it uses single-dash PowerShell parameter
  names (`--stage` is not a parameter prefix for every PowerShell host).
  Smoke leg 2 now applies the delta with the installation's own
  `vira-updater.exe` and asserts the helper survives the upgrade; a missing
  helper reports a clear Persian error instead of a `FileNotFoundError`
  traceback. Tests: `TestUpdaterDiscovery`.

### Added
- **داشبورد** — six KPI cards (assets, liabilities, equity, net income for the
  current fiscal year, warehouse value, net cash), four theme-aware ECharts
  panels (financial structure, P&L, daily sales trend, warehouse composition),
  an alert strip (unbalanced books, stock-out alarms with the suggested
  supplier, open production jobs, new orders, available update) and the
  recent-orders / active-jobs queues.
- **انبار** — items (filament spools and produced goods), stock movements
  (append-only, with insufficient-stock refusal), the stock-out alarm list with
  per-item supplier suggestion, and suppliers scored on quality / delivery /
  price.
- **سفارش‌ها** — order intake priced by the sheet engine, status lifecycle
  (NEW → … → DELIVERED), proforma document (PDF, HTML fallback), and the
  daily/weekly/monthly/annual sales report.
- **تولید** — production jobs per order line: start / finish (consumes the
  filament grams × quantity, adds the finished models to stock) / cancel, with
  planned-vs-done summary and the required-filament figure.

## [1.0.4] — 2026-10-15

v1.0.3 installed and ran correctly, but published **no delta packages** — the
delta builder guessed the previous release's portable-zip filename and silently
skipped every base it could not fetch, so updates fell back to the full
installer.

### Fixed
- **Split ordering is deterministic** — `uuid7` is now monotonic within the
  process (RFC 9562 §6.2 method 3: a counter absorbs same-millisecond calls).
  Previously two ids minted in the same millisecond carried random tails, so
  sorting splits by id could swap an entry's debit and credit rows at display
  time. New tests: `test_ids.py`.
- **Delta discovery** — `build_deltas` now asks the GitHub API for each previous
  release's portable asset (the filename varied: `VIRA-v1.0.0.zip` vs
  `vira-v1.0.2-portable.zip`) instead of guessing, and its `latest.json`
  `deltas[]` entries point at assets that are actually published.
- **Smoke leg 2 is the real update path** — it downloads the previous release's
  portable install, applies the matching delta with the shipped updater, and
  asserts the install reaches the new version with rewritten manifests (and a
  delta strictly smaller than the setup). The old leg applied a delta onto a
  fresh same-version install, which never happens in the field.

### Added
- **`vira-<version>-app.zip`** — the exact install-layout payload (`{app}`
  directory, with `install_manifest.json`), published with every release. It is
  the delta base for all future updates, and doubles as a true portable app
  (unzip + `start_vira.cmd`). The older `*-portable.zip` bundles are source
  trees and cannot serve as delta bases.

### Verified
- v1.0.3's install experience: silent install, shortcut resolution via the
  Windows shell, first-run migrate+seed+credentials, healthy SPA on
  `http://127.0.0.1:8787` — all CI-gated (smoke legs 1 and 5).

### Notes
- Users updating from v1.0.2/v1.0.3 download the full installer one last time
  (those releases shipped no reconstructible payload base). From v1.0.4 onward
  updates are delta-only whenever changed parts exist.

## [1.0.3] — 2026-10-15

Fixes the broken installed experience reported after v1.0.2 (shortcut points
at a missing file; launch does nothing).

### Fixed
- **Shortcuts targeted a file that never existed.** The installer pointed
  Desktop/Start-Menu/Startup shortcuts and the finish-page «اجرای V.I.R.A» at
  `{app}\start_vira.cmd`, but no such file was ever created — hence
  «Missing Shortcut» and silent launch failures. `scripts/start_vira.cmd` now
  ships at the payload root: finds Python (bundled → dev venv → PATH), runs the
  safe migration + seed (idempotent), mints and shows owner credentials on
  first run (`%LOCALAPPDATA%\VIRA\first-run-credentials.txt`), starts uvicorn
  in a visible log window and opens `http://127.0.0.1:8787` when health is green.
- **Bundled CPython 3.11** (python-build-standalone via uv) is now staged with
  the app — the installed app runs on machines without a system Python.
- **SPA serving in the installed layout** — `spa_static_dir()` now resolves
  `{app}\static` (installed) as well as `<repo>/frontend/dist` (dev); before,
  the mounted path pointed outside the install directory and `/` was a 404.
- **`migrate_vira.py` on installed payloads** — `backend/alembic(.ini)` is
  staged alongside the app so first-run migrations work.
- **Delta baseline integrity** — `gen_delta` now packs `install_manifest.json`
  + `version.json` into every delta (the updater rewrites them after apply;
  without them the next delta would diff against a stale baseline).
- **Delta patches without `tools\bspatch.exe`** — `scripts/bspatch.py`
  (pure-Python, wraps the tested engine applier) is the updater's fallback,
  run by the bundled interpreter.
- **New smoke leg 5** resolves every installed shortcut via the Windows shell
  (any missing target fails CI), then really launches the app and asserts
  `/api/v1/health/live`, the SPA at `/`, and the first-run credentials file.

## [1.0.2] — 2026-10-15

First **published** release. `v1.0.0` and `v1.0.1` tags exist but were never
published (pipeline debugging; tags are immutable, so each fix shipped as a
new patch version). Validated end-to-end via `[release-dry-run]` runs before
tagging: Inno Setup compile, `vira-updater.exe` (ps2exe), delta generation,
and the Windows install/upgrade/rollback smoke test all pass.

### Fixed — release pipeline
- `InitializeUninstall` must be a Boolean function (Inno compile error).
- `x64` instead of `x64compatible` for broad Inno 6 compatibility.
- Smoke harness: forced-failure rollback fires after the snapshot (the thing
  being tested); updater `Fail` throws (catchable) instead of `exit`; the
  forced-failure stage carries its own `update.json`; `/DIR` quoted.

## [1.0.1] — 2026-10-15 (never published)

First **published** release — the complete 8-phase plan with a green CI/CD
pipeline. The `v1.0.0` tag exists but was never published (the workflow file
was invalid at load time; tags are immutable, so fixes ship as `v1.0.1`).

### Fixed — CI/CD pipeline (all five jobs green)
- Workflow validation: `runner.temp` is illegal in job-level `env` — moved to
  step-level env (every run before this failed at load time).
- Declared `bandit` + `pip-audit` in the dev extra (`uv run` died command-not-found).
- `uv sync --frozen` installs no extras — CI syncs with `--all-extras`.
- Prettier: 16 files formatted that the Phase 6 check never wrote.
- Dev-mode boot: `optimizeDeps.exclude` on react-dropzone/react-pdf served raw
  CJS deps (`attr-accept`, `warning`) with no default export — the app never
  mounted in dev (blank page). Full prebundling; pdf.worker via `?url`;
  `pdfjs-dist` as a direct dependency.
- Journal form: the live zero-balance error never rendered (RHF 7.90
  useFieldArray swallows array-level resolver errors) — rendered from the
  computed totals; zod remains the submit gate.
- E2E: deterministic `/login` flow with seeded owner user, account selection
  in the journal test, webServer 120 s timeouts.

## [1.0.0] — 2026-10-15 (never published)

(Superseded by 1.0.1 before publication — see above.) First public release
of the complete 8-phase plan (Persian accounting, Windows-native, SQLite-only).

### Added — Phases 1–7
- Phase 1–2: product spec + data model, FastAPI backend (SQLAlchemy 2.0 +
  Alembic), scaled-INTEGER money (×10 000; FX ×1e8) with decimal.js at the
  presentation edge, Persian RTL Jalali UI (React 19 + TS + Vite + TanStack).
- Phase 3–4: full SPA (journal, accounts, bank import, reconciliation,
  statements, price calculator, receipts), persistence layer (TypeDecorator
  money columns, FTS5 search, idempotency keys, keyset pagination,
  reconciliation sessions, monthly snapshots, encrypted backups).
- Phase 5: RBAC + TOTP/recovery codes + 5-minute sudo step-up, login rate
  limiting, HMAC webhooks, resilient external clients, security headers,
  Idempotency-Key on every mutation, draft recovery on 401.
- Phase 6: GitHub Actions CI/Release without service containers, safe SQLite
  migration lifecycle (migrate_vira.py/.ps1), sudo-gated System & Operations
  page/API, rotating logs, `/health/ready`, Dependabot, ESLint 9 + Prettier.
- Phase 7: unified search (FTS5 + LIKE parameterized, Decimal numeric tokens,
  RapidFuzz), pluggable storage (local + S3-compatible, sha256 content-addressed,
  presigned delivery, faceted receipt viewer), Persian-only react-i18next
  namespaces, Jalali fiscal year (1 Farvardin) + Jalali print-to-PDF headers,
  privacy-first Umami analytics with zero-PII redaction.

### Added — Phase 8: Installer, Versioned Releases & In-App Delta Updates
- Inno Setup 6 installer (`installer/vira.iss`) with the mandatory «مسیر نصب»
  (select where to install) page, `InstallDir` recorded in `HKLM/HKCU\SOFTWARE\VIRA`,
  optional tasks (desktop/Start menu/launch-at-login/backup job), and an
  uninstaller that keeps `%LOCALAPPDATA%\VIRA` user data unless explicitly opted in.
- Delta update engine (`backend/app/services/update_engine.py`): per-file
  SHA-256 manifests, manifest diffing, `VIRA-vX.Y.Z-delta-from-vA.B.C.zip`
  packages (`update.json` + `files/` + bsdiff `patches/` + `delete.json`),
  client-side selection (delta → delta chain → full installer), BSDIFF40 apply.
- Update channel (`backend/app/services/update.py`): GitHub Releases +
  `latest.json` (schema_version 1, unknown versions refused), ETag caching,
  403/429 Persian retry-later, `APP_UPDATE_URL` mirror override, optional
  Ed25519 signature verification (`scripts/sign_update.py`).
- Transactional updater helper (`scripts/vira_updater.ps1` → `vira-updater.exe`):
  mutex + lock file, graceful stop, rollback snapshot, verified apply, manifest
  rewrite, relaunch; any failure restores the previous version
  («خطا در به‌روزرسانی. نسخهٔ قبلی بازگردانی شد.»).
- In-app update UX: «بررسی به‌روزرسانی» + startup badge + mandated dialog
  «به‌روزرسانی جدید موجود است» / «به‌روزرسانی جدیدی در دسترس است (نسخهٔ X.Y.Z).
  آیا می‌خواهید دانلود و نصب شود؟» with «دانلود و نصب» / «بعداً» / «مشاهدهٔ جزئیات»,
  download progress, verification status and restart-to-finish step.
- CI: release workflow compiles the installer + `vira-updater.exe`, generates
  deltas vs the last K = 3 tags, uploads the setup as a GitHub Actions artifact
  and as an immutable Release asset; Windows smoke test (silent install, delta
  upgrade with size assertion, data-preservation checksum, forced-failure
  rollback).
