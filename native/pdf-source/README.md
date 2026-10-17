# Private, source-verifiable Windows PDF experiment

This profile is **not** an approved redistributable, installer input or delta input.
The existing 27 SDK DLLs remain unreviewed; this experiment does not relabel them.

## Rebuild

On a disposable Windows x64 GitHub Actions runner with Visual Studio C++ build
tools / Windows SDK, Git, PowerShell, uv, Node 22 and pnpm 9, use the checked-in
`pdf-source-proof.yml` workflow. `scripts/source_pdf_build.ps1` checks out the
**exact** `builtin-baseline` commit from this directory's manifest, bootstraps that
vcpkg revision, and invokes:

```powershell
vcpkg install --triplet x64-vira-pdf --host-triplet x64-windows `
  --x-manifest-root=<this-directory> --x-install-root=<temporary-installed> `
  --overlay-triplets=<this-directory>/triplets --binarysource=clear --no-print-usage
```

`VCPKG_BINARY_SOURCES=clear` also disables binary package restoration. Target
libraries and required host ports are built on that runner. Bootstrap executables,
compiler, SDK and downloaded build tools are prerequisites, **not claimed to be
source-built**. This is traceability, not bit-for-bit reproducibility or an offline
compiler SDK. Upstream source archive hashes and patches are in the pinned port
recipes; tool-download hashes are in pinned vcpkg scripts.

The experimental triplet uses dynamically linked libraries (LGPL libraries remain
replaceable) with a static MSVC CRT and release-only target builds. This setting
is a hypothesis to verify in the build and PE closure, not a promise about port
support, license compatibility, OS support or redistribution rights. Host tools
use the ordinary x64-windows triplet and are **not** copied into the native candidate.

## Evidence, and what it does not prove

The collector fails if a selected DLL has no installed package owner, a non-inbox
DLL import is unresolved, a native target package has no captured patched source,
or target copyright / SPDX receipts are absent. It captures all target package
sources, including static dependencies, rather than just the owners of selected
DLLs. Full vcpkg recipes, patches, bootstrap scripts, license and version database
are captured alongside complete patched `buildtrees/<port>/src` trees and installed
notices. Source tree hashes cover sorted relative UTF-8 paths and SHA256 file hashes.
The source ZIP SHA256 is recorded in `source-inventory.json`. Installed receipts
and generated toolchain/ABI records are separate evidence.

The complete patched source can contain upstream test resources; no installed
runtime DLLs, build-tree output directories or downloaded tool executables are
added to the evidence archive. The actual native candidate is temporary CI storage
only and has `DO_NOT_DISTRIBUTE.txt`. Artifacts contain source, license/metadata,
logs and synthetic PDFs, not a runtime bundle.

The real production-staged CPython proof is repeated with this candidate, in a
Persian/spaced application path. It verifies imports, library origin, integer and
double callbacks, A4 pages, and embedded Vazirmatn 400/700 including all 30 digits.
It still uses the explicitly private **ASCII temporary Fontconfig path**; production
Unicode bootstrap is a separate open gate.

A green build means captured-source technical evidence, **not legal approval**.
Explicit license choices (including dual-license choices), notice completeness,
compiler/CRT terms, durable corresponding-source delivery alongside any future
binary distribution, production bootstrap, native manifest/delta/rollback and final
installed-user acceptance remain separate gates. No workflow here creates a release
or tag, publishes compiled DLLs, changes an installed user database or changes pricing.
