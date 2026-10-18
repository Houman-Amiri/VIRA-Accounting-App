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
sidecar do not need to run the exporter or provision an application Python
environment. vcpkg may download/use its own build tools, including Python/Meson;
that is distinct from depending on VIRA's app environment. The old
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
python -B scripts/audit_pdf_native_rebuild.py `
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

## Consume the captured LOCAL preferred-source trees

The default command above still downloads target source archives. It is NOT the
local replay route. The separate `prepare_pdf_local_sources.py` adapter and
`pdf-local-source-port-pins.json` are explicit MIT build-tool derivatives; they
are included in the **14-file** sidecar, not a repository-wide grant.

For the new source kit containing that sidecar, authenticate the kit manifest
SHA256 and trusted verifier independently first. With standard-library Python
3.11+ (no VIRA Python environment or `pefile` needed for preparation):

```powershell
python -I -S C:/source-kit/licensed-build-files/scripts/pdf_source_kit.py `
  --verify C:/source-kit --expected-manifest-sha256 TRUSTED_MANIFEST_SHA256 `
  --extract-sources C:/new-preferred-inputs

python -I -S C:/source-kit/licensed-build-files/scripts/prepare_pdf_local_sources.py `
  --kit C:/source-kit --expected-manifest-sha256 TRUSTED_MANIFEST_SHA256 `
  --sources C:/new-preferred-inputs --out C:/new-local-overlay

cd C:/source-kit/licensed-build-files
pwsh -NoProfile -File scripts/rebuild_pdf_native.ps1 `
  -WorkDir C:/new-local-native-build -OverlayPorts C:/new-local-overlay

python -I -S scripts/prepare_pdf_local_sources.py `
  --check-inputs C:/new-local-overlay/local-source-preparation.json
```

All output/work paths must be **new and outside the input kit/preferred tree**,
not the installed app/data directory. Extraction and overlay preparation reject
nested output directories before creating them, including resolved aliases.
Windows must permit real symlink creation; no flattened substitute is accepted.
The extractor restores the ZIP-recorded local modification times of regular
files (two-second ZIP precision). Autotools can regenerate configure/Makefile.in
when fresh extraction-order mtimes invert their dependencies. Preserving those
relative times avoids that unintended toolchain regeneration; it does not claim
an absolute UTC timestamp or bitwise reproduction.
Use a short ASCII build path. Quotes, semicolons, dollar signs, square brackets
and newlines in preferred-input paths are deliberately unsupported/rejected
rather than interpolated as executable CMake text.

The adapter checks the authenticated original kit/source ZIP, every original
package digest, archived port recipe SHA256 and its LF-canonical pin, exact
acquisition count and expected root layout **before creating the overlay**.
The original capture has exactly one root for each of 19 packages and an empty
`pthread` alias; unexpected additional/renamed roots are rejected, not silently
selected. Safe relative file symlinks are retained. External/dangling/directory
links, junctions and executable CMake path injection are refused.

Only target `x64-vira-pdf` source acquisition calls in the pinned recipes are
replaced. Host recipes retain the original LF-canonical text beside the adapter. Bootstrap,
compiler, Python/Meson, MSYS and host-tool downloads still work: download helper
functions are **not globally overridden**. This is not a network-isolated or
bitwise-reproducible compiler SDK.

For each target recipe, CMake copies the verified already-patched preferred
root into that port's fresh vcpkg buildtrees `src` directory. It never patches,
cleans or writes the external input kit/source tree. The disposable buildtrees
source area is replaced to avoid mixing host and target roots. Preserve basenames
so the final tree audit remains meaningful. PCRE2's SLJIT subtree is already
merged and must NOT be deleted/remerged. libpng's optional APNG feature is
explicitly rejected because this captured baseline did not contain that patch.
Other unreviewed feature/source variants need a separately reviewed adapter.

### Explicit local modifications

After verified extraction, make permitted library edits in the **new input
copy**, never the immutable original ZIP. Re-run preparation with
`--allow-modified` to acknowledge them. Without that option changed preferred
source bytes fail closed. Review `local-source-preparation.json`, including
original/current tree hashes and `changed_packages`, before compiling.

`local-source-reference.json` is a distinct audit reference: it preserves
`original_source_archive` as provenance, sets `source_archive` to null, and does
**not** claim that the old ZIP is the complete corresponding source of changed
new DLLs. A new corresponding-source archive has not been assembled/published.
Keep the exact edits and full modified preferred sources for that future task,
including required prominent modification notices/dates before redistribution.
Use this generated reference with the optional native inspector, rather than
expecting changed libraries to retain the old baseline hashes:

```powershell
python -B scripts/audit_pdf_native_rebuild.py `
  --sidecar C:/source-kit/licensed-build-files --work C:/new-local-native-build `
  --reference C:/new-local-overlay/local-source-reference.json `
  --out C:/evidence/local-native-audit.json
```

The separate local replay CI deliberately changes Pango's exported version
string and requires its actual DLL function to return the edited string, along
with all 20 tree digests, 21 DLL origins/owners/closure and unchanged external
input hashes. A generated overlay or passing synthetic test is not that proof;
the actual build/audit 39146630126 on 576c0ea passed, returning
`1.58.0-vira-local-source`. See
[the phase report](../reports/pdf-local-preferred-source-replay-fa.md) and
[the pinned witness](pdf-local-source-replay-proof.json). Use `-B` for the optional
inspector to avoid adding Python bytecode caches to a source-kit envelope. Even a successful
modified DLL test is **not** installed-app LGPL replacement/EULA acceptance.
