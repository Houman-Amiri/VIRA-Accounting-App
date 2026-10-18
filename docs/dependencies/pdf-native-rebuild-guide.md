# Native-only PDF library rebuild (not an application installer)

This is for a recipient/developer rebuilding native PDF libraries. **End users
must not install Visual Studio, rebuild libraries, or reinstall VIRA just to use
an approved future app update.** No app data or installed VIRA directory is used.

## Prerequisites and boundaries

- Windows x64, PowerShell **7**, Git, and an appropriately licensed MSVC C++
  toolchain/Windows SDK. Toolchain licensing is a separate prerequisite, not
  granted by VIRA's limited MIT build-file license.
  See `pdf-crt-official-reference-review.json` for the actual 2026 agreements.
  In particular, the Build Tools OSS-dependency build exception has conditions;
  it is not a blanket right to develop arbitrary modifications or redistribute
  Microsoft's components. Runtime installation rights are not redistribution
  rights. Do not infer entitlement from a hosted runner's Enterprise path.
- Internet access for the immutable vcpkg checkout, verified upstream source
  archives, and vcpkg's build tools. This is **not an offline compiler SDK**.
- No backend/frontend checkout, Node, pnpm, uv, application Python environment,
  database, Inno Setup, or app staging script is required by the native entry point.
- A **new, absolute work directory**, preferably a short ASCII build path. Do not
  use the app installation directory, data directory, or an existing work tree.
  Existing directories are rejected even in plan-only mode.

## Obtain the licensed build files

The scope in `pdf-build-script-license-scope.json` now includes the native-only
entry point and its native audit helper, derivatives within the owner-approved
MIT build-tooling scope. The accounting app and unlisted files are not relicensed.
Keep `LICENSES/VIRA-PDF-BUILD-MIT.txt` and the scope document with the source files.

A maintainer can export the minimal source/permission sidecar from this checkout:

```powershell
python scripts/check_pdf_build_license.py --sidecar C:/new-licensed-build-files
```

The **exporter** uses only standard-library Python. Recipients of the exported
sidecar do not need Python for the native compilation command below. The old
`source_pdf_build.ps1`/GitHub proof workflow still references app staging; do not
use it as the independent entry point.

## Plan and build

From the exported sidecar (not the VIRA application checkout):

```powershell
pwsh -NoProfile -File scripts/rebuild_pdf_native.ps1 `
  -WorkDir C:/new-vira-native-build -PlanOnly

pwsh -NoProfile -File scripts/rebuild_pdf_native.ps1 `
  -WorkDir C:/new-vira-native-build
```

The plan does not create the work directory. Compilation creates it once,
checks out vcpkg `a5f736224e85b32e25a8ffc52562333180396642`, and runs the manifest
with target `x64-vira-pdf` and host `x64-vira-pdf-host`. Both command-line and
environment binary-cache sources are cleared. Target libraries are dynamic DLLs
with static CRT/release-only settings; build-only host tools use dynamic CRT.
Downloaded bootstrap/build executables are **not claimed to be source-built**.

Outputs remain under the new work directory:

- `installed/x64-vira-pdf/bin`: unfiltered build output, **not** an installer input.
- `build.log`, `rebuild-plan.json`, `rebuild-result.json`: logs, settings and hashes.
- `DO_NOT_DISTRIBUTE.txt`: project release-readiness marker, not an extra restriction
  on MIT source rights.

The script never calls app staging, PDF app templates, an installer, or a database.
No existing work tree is deleted or reused. After a failure, inspect its logs and
choose a new work directory rather than silently cleaning/reusing it.

## Modified libraries

MIT permits modifying the build scripts. vcpkg overlay ports are also supported:

```powershell
pwsh -NoProfile -File scripts/rebuild_pdf_native.ps1 `
  -WorkDir C:/new-modified-native-build -OverlayPorts C:/my-modified-ports
```

An overlay can point to preferred sources/patches you modified according to the
upstream library's license. Keep required notices, source and modification records.
The reference-hash checker/baseline CI audit intentionally detects changed inputs;
that is **not** a prohibition on MIT/LGPL-permitted modifications. The build itself
does not require original library-output hashes and does not enforce app signatures.

## Optional baseline audit, distinct from compilation

`audit_pdf_native_rebuild.py` compares target package/source trees and PE closure
against the recorded reference, and on Windows loads the selected libraries to
check their actual origins. This optional inspector needs Python and
`pefile==2024.8.26` (wheel SHA256
`76f8b485dcd3b1bb8166f1128d395fa3d87af26360c2358fb75b80019b957c6f`). It does not
need app dependencies. Supply the reference source inventory explicitly:

```powershell
python scripts/audit_pdf_native_rebuild.py `
  --sidecar C:/new-licensed-build-files --work C:/new-vira-native-build `
  --reference C:/evidence/pdf-runtime-win64-source-inventory.json `
  --out C:/evidence/native-rebuild-audit.json
```

The reference is for the original baseline, not a claim that altered libraries
must retain original source hashes. For modified libraries, use a reviewed updated
reference instead of calling the original-baseline audit a legal restriction.

## Distribution remains separate

Successful compilation or native DLL loading alone is not proof of PDF rendering
with the new build, bitwise reproducibility, CRT redistribution entitlement,
LGPL DLL replacement in the installed app, production bootstrap, or native delta/
rollback. See the separate source-delivery plan and phase report. No compiler,
SDK, compiled DLL directory, application bundle or release is uploaded by this
independent proof workflow; artifacts contain diagnostic metadata/logs only.
