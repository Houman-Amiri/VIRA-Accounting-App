# Limited native PDF build-file license

`VIRA-PDF-BUILD-MIT.txt` applies **only** to VIRA-authored content in the explicitly
listed reference files in
[`pdf-build-script-license-scope.json`](../docs/dependencies/pdf-build-script-license-scope.json)
and to derivatives permitted by MIT. There is **no wildcard or repository-wide
MIT grant**. The project owner confirmed this limited scope on 2026-10-18.

Keep the full MIT copyright/permission/warranty notice and the scope document
with the licensed source copies. All pre-existing third-party rights and notices
remain applicable; this grant does not relicense upstream library/CRT code.

It does **not** change the license of the accounting application, backend,
frontend, installer or other unlisted files. It is not approval to release the
native runtime or publish a new application version. In particular, not every
application/staging script referenced by the historical full proof workflow is
included in this grant.

Check the exact scope and reference hashes (standard-library Python only):

```bash
python scripts/check_pdf_build_license.py
```

Create a **new** limited source/permission sidecar directory, without binaries or
unlisted application files:

```bash
python scripts/check_pdf_build_license.py --sidecar /path/to/new-licensed-build-files
```

The directory must not already exist. The checker normalizes CRLF to LF only
for source-version identification, so Windows checkout endings do not invalidate
the grant. It does not normalize Unicode or ignore source changes. The original
corresponding-source ZIP is left untouched; seven of its captured VIRA file
versions match the authorized reference versions. The missing inventory-import
helper is supplied in the sidecar. Independent whole-workflow rebuild completeness,
third-party/CRT terms and recipient source availability remain separate gates.

The runtime's `BLOCKED` flag describes this project's release-readiness decision;
it is **not an additional restriction on rights granted by the MIT license**.

## Current build-tool derivatives

The current explicit allowlist has **12 files**: the historical nine, native-only
rebuild/audit helpers, and `scripts/pdf_source_kit.py`. The latter assembles and
checks a private source/recipe/notices kit with standard-library Python; it never
publishes, installs a runtime or grants third-party/CRT permission. All reference
hashes and the seven historical source-archive bindings remain checked. Kit
consistency is not publisher authentication without an independently trusted
external digest/verifier. See `docs/dependencies/pdf-source-kit-proof.json` and
`docs/reports/pdf-source-kit-and-crt-probe-fa.md`. No root application license.
