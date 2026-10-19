"""Application-owned PDF dispatch and document lifetime, default behavior unchanged.

The private policy is a Python factory argument, NOT a setting, environment switch,
HTTP parameter, distribution approval, or installed-runtime integration. Native
bootstrap (audited DLLs, UTF-8 and Windows ACP) remains the caller's prerequisite.
No QA scripts, renderer monkeypatches or caller-supplied configuration factories.
"""
from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True, slots=True)
class PrivatePdfPolicy:
    """Explicit private-candidate opt-in; contains paths, never executable hooks."""

    cache_root: Path

    def __post_init__(self) -> None:
        if (not isinstance(self.cache_root, Path) or not self.cache_root.is_absolute()
                or '..' in self.cache_root.parts or self.cache_root == Path(self.cache_root.anchor)):
            raise ValueError("Private PDF cache requires a non-root absolute path without traversal")


class PdfRenderer:
    """Per-application selection, per-document native resources; no global mode."""

    def __init__(self, private_policy: PrivatePdfPolicy | None = None) -> None:
        if private_policy is not None and not isinstance(private_policy, PrivatePdfPolicy):
            raise TypeError("Only an explicit PrivatePdfPolicy is accepted")
        self._private_policy = private_policy

    @property
    def mode(self) -> str:
        return "LEGACY_DEFAULT" if self._private_policy is None else "PRIVATE_EXPLICIT_FONTCONFIG"

    def __call__(self, template_name: str, context: dict[str, Any]) -> bytes:
        # Resolve dynamically so legacy callers/diagnostics retain their contract.
        from . import pdf

        if self._private_policy is None:
            return pdf.render_pdf(template_name, context)

        from .pdf_fontconfig import private_font_configuration

        root = self._private_policy.cache_root
        # Cooperative safety, not an ACL/security boundary against a racing owner.
        self._check_cache_path(root)
        root.mkdir(parents=True, exist_ok=True)
        self._check_cache_path(root)
        # Each document owns only this child, never the root or unrelated files.
        with tempfile.TemporaryDirectory(prefix="document-", dir=root) as directory:
            with private_font_configuration(Path(directory)) as configuration:
                data = pdf.render_pdf(template_name, context, font_configuration=configuration)
                if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
                    raise RuntimeError("Explicit PDF renderer did not return PDF bytes")
            return data  # adapter cleanup MUST succeed before returning bytes

    @staticmethod
    def _check_cache_path(root: Path) -> None:
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError("Private PDF cache must not traverse symlinks")
        if root.exists() and not root.is_dir():
            raise ValueError("Private PDF cache must be a directory")
