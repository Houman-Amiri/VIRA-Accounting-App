"""Application-owned PDF dispatch and document lifetime, default behavior unchanged.

The private policy is a Python factory argument, NOT a setting, environment switch,
HTTP parameter, distribution approval, or installed-runtime integration. Native
bootstrap (audited DLLs, UTF-8 and Windows ACP) remains the caller's prerequisite.
No QA scripts, renderer monkeypatches or caller-supplied configuration factories.
"""
from __future__ import annotations

import hashlib
import logging
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


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
        # Plain-value diagnostic events only: never retain native pointers/configs
        # in logging records, and never accept a caller's executable observer hook.
        document_id = uuid.uuid4().hex
        log.info("private_pdf_lifecycle", extra={"pdf_document": {"event": "started", "id": document_id}})
        try:
            with tempfile.TemporaryDirectory(prefix="document-", dir=root) as directory:
                with private_font_configuration(Path(directory)) as configuration:
                    data = pdf.render_pdf(template_name, context, font_configuration=configuration)
                    if not isinstance(data, bytes) or not data.startswith(b"%PDF-"):
                        raise RuntimeError("Explicit PDF renderer did not return PDF bytes")
                    snapshot = self._snapshot(configuration)
                folder = snapshot["font_folder"]
                if folder is not None and Path(folder).exists():
                    raise RuntimeError("Private PDF temporary fonts were not cleaned")
            log.info("private_pdf_lifecycle", extra={"pdf_document": {
                "event": "completed", "id": document_id, **snapshot,
                "cache_folder": directory, "cache_temp_cleaned": not Path(directory).exists(),
                "font_temp_cleaned": folder is None or not Path(folder).exists(),
            }})
            return data  # both adapter AND cache cleanup precede successful return
        except BaseException:
            # No template/context/customer/cookie or exception locals in events.
            log.info("private_pdf_lifecycle", extra={"pdf_document": {
                "event": "failed", "id": document_id}}, exc_info=True)
            raise

    @staticmethod
    def _snapshot(configuration: Any) -> dict[str, Any]:
        folder = getattr(configuration, "_folder", None)
        fonts = sys.modules.get("weasyprint.text.fonts")
        native = getattr(configuration, "_config", None)
        system = None
        if native is not None and fonts is not None:
            system = int(fonts.fontconfig.FcConfigGetFonts(native, fonts.fontconfig.FcSetSystem).nfont)
        return {
            "font_folder": str(folder) if folder is not None else None,
            "font_sha256": sorted(hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in Path(folder).iterdir() if p.is_file()) if folder is not None else [],
            "system_fonts": system,
            "preferred_encoding": getattr(fonts, "PREFERRED_ENCODING", None),
        }

    @staticmethod
    def _check_cache_path(root: Path) -> None:
        if any(p.is_symlink() for p in (root, *root.parents)):
            raise ValueError("Private PDF cache must not traverse symlinks")
        if root.exists() and not root.is_dir():
            raise ValueError("Private PDF cache must be a directory")
