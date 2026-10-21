# Phase3 private installed-version contract — not public activation/release

Status: implemented and locally tested; fresh Windows evidence required.

## Explicit mode, not an environment bypass

- Legacy `PrivateBootstrapPlan` requests keep their exact fixed-version guard
  (`0.0.0-private-unicode-proof`). No marker, manifest rewrite or SDK plan alone
  can opt into versioned Source21 startup.
- Installed SOURCE plans require BOTH an external anchor path and its SHA256,
  plus an independent source-audit digest. The path must be disjoint from the
  payload and, at activation, below the disposable runner-owned profile. The
  standard CPython isolation, Unicode/CWD, fresh workspace and pre-import rules
  still apply. Full byte/inventory/origin/ACP checks remain in force.
- Anchor schema2 retains the existing exact private role and adds exactly one
  field, `version`, an ASCII canonical `major.minor.patch` triplet. Schema1 is
  retained only for legacy contracts/fixtures. Installed bootstrap requires v2.
- The entire manifest is checked BEFORE executing its app-owned anchor parser.
  Its three digests must match the plan; `version.json` is a manifest-covered
  member and must equal the external version. Anchors are hashes, not signatures
  or a grant of public distribution rights.
- The genuine bridge emits a separate `PRIVATE_INSTALLED_SOURCE_DESKTOP_REQUEST`
  through the SAME actual CMD entry. The app checks the external anchor digest,
  canonical profile location, state ownership, port, browser policy and pins.
  Legacy requests cannot smuggle the extra installed fields. Public startup is
  unchanged. No QA factory, renderer, migration or ASGI hook is injected.

## Update boundary

Generator/stager/controller bind schema2 target version to archive metadata and
reject schema downgrade. The private stager/controller permit the private ACP
receipt as application metadata; public staging remains closed to private
packages/operations. Existing archive SHA verification and anchored old-helper
selection are unchanged. Old/target anchors remain separate transactional inputs.

## Historical evidence versus new execution

Phase3 extends two previously frozen runtime modules and their source workflow.
Exact old bytes of these THREE files are retained under
`phase2-frozen-implementation/`, matched to the ORIGINAL proof pins, not rewritten
hashes. The other13 pinned files remain current-byte checked. These documentation
snapshots are never executed. Old Phase2 Windows evidence does NOT certify this
new code. Existing legacy negative tests and full regression suite still run.

28 new synthetic tests include full ZIP/BSDIFF construction, full synthetic
Source21 assembly and read-only re-verification, version/pin/port/state mismatch,
ambiguous versions and public-path rejection. Fake DLL/interpreter/helper bytes
are NEVER executed. The first full run found a historical-evidence assertion
because the extended workflow had not yet been archived; corrected by retaining
its exact old bytes, NOT changing the original proof hash or skipping the test.
Final full suite:1059 PASS87.59s, no failures/errors/skips; Ruff, Mypy90, Bandit
CI-level `-ll`, dependency audit PASS (local tooling seed setuptools84.2.1).

## Fresh Windows acceptance path

The existing cold-source workflow re-runs legacy SDK/Source/CMD regressions, then
builds a version99.30.0 private Inno installer from the freshly audited21-DLL
closure and locked app. A new external-only driver checks exact selected-path
installation/anchor bytes, two independent app-owned real-CMD HTTP lifecycles,
owner auth/CSRF/sudo, actual running version, parallel PDFs/font inspection,
session/secret/IDs preservation, unchanged payload and ordinary-data sentinel.
Only logs/JSON/synthetic PDFs are uploaded, never app/DB/interpreter/native DLLs.

Until the run is collected, this is a proposed execution path, NOT a passing
Windows claim. Even a successful install/start/restart does NOT complete Phase3:
independently audited changed-native target, permissioned real in-app delta,
verified rollback/data invariants, and crash/stale-lock recovery remain required.
All six distribution gates OPEN. No new public version/tag/release authorized.
