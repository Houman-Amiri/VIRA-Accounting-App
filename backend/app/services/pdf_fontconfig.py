"""Explicit, private-candidate Fontconfig bootstrap; NOT enabled in normal rendering.

Use the native in-memory UTF-8 API, not Fontconfig's Windows CRT getenv path.
This adapter targets the locked WeasyPrint 70.0 FontConfiguration contract.
It neither selects/ships DLLs nor establishes their redistribution permission.
"""
from __future__ import annotations

import shutil
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from importlib.metadata import version
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import Element, SubElement, tostring

_BINDING_LOCK = threading.Lock()


def configuration_xml(cache_dir: Path) -> bytes:
    """Only application font faces; no system directories or external includes."""
    if cache_dir.is_symlink() or not cache_dir.is_dir():
        raise ValueError("An existing private font-cache directory is required")
    root = Element("fontconfig")
    SubElement(root, "reset-dirs")
    SubElement(root, "cachedir").text = cache_dir.resolve().as_posix()
    return tostring(root, encoding="utf-8", xml_declaration=True)


def _bindings() -> Any:
    if version("weasyprint") != "70.0":
        raise RuntimeError("Private Fontconfig adapter requires the reviewed WeasyPrint 70.0 contract")
    from weasyprint.text import fonts  # type: ignore[import-untyped]

    # Extend declarations, not native implementations or process environment.
    with _BINDING_LOCK:
        if not hasattr(fonts.fontconfig, "FcConfigCreate"):
            fonts.ffi.cdef("FcConfig *FcConfigCreate(void); FcBool FcConfigBuildFonts(FcConfig *config);")
    return fonts


@contextmanager
def private_font_configuration(cache_dir: Path) -> Iterator[Any]:
    """One document's explicit native config, with no global config/CWD/TEMP mutation.

    Normal FontConfiguration.__init__ loads a configuration through CRT getenv.
    Allocate its Python container without that initializer and use the public
    Fontconfig/Pango C APIs instead. Internal Python fields are version-guarded.
    Callers must finish rendering before leaving this context.
    """
    xml = configuration_xml(cache_dir)
    fonts = _bindings()
    ffi, fc = fonts.ffi, fonts.fontconfig
    instance = fonts.FontConfiguration.__new__(fonts.FontConfiguration)
    instance._folder = None
    instance.strut_layouts = {}
    instance.font_features = {}
    config = fc.FcConfigCreate()
    if config == ffi.NULL:
        raise RuntimeError("Fontconfig configuration allocation failed")
    font_map = None
    try:
        if not fc.FcConfigParseAndLoadFromMemory(config, xml, True) or not fc.FcConfigBuildFonts(config):
            raise RuntimeError("Explicit UTF-8 Fontconfig configuration failed")
        system = fc.FcConfigGetFonts(config, fc.FcSetSystem)
        if system == ffi.NULL or system.nfont != 0:
            raise RuntimeError("Private document configuration must not inherit system fonts")
        raw_map = fonts.pangoft2.pango_ft2_font_map_new()
        if raw_map == ffi.NULL:
            raise RuntimeError("Pango font-map allocation failed")
        try:
            font_map = ffi.gc(raw_map, fonts.gobject.g_object_unref)
        except BaseException:
            fonts.gobject.g_object_unref(raw_map)
            raise
        fonts.pangoft2.pango_fc_font_map_set_config(ffi.cast("PangoFcFontMap *", font_map), config)
        instance.font_map = font_map
        instance._config = config
    except BaseException:
        if font_map is not None:
            ffi.release(font_map)
        raise
    finally:
        # Pango keeps its own reference after set_config; release ours exactly once.
        fc.FcConfigDestroy(config)
    try:
        yield instance
    finally:
        instance.strut_layouts.clear()
        instance.font_features.clear()
        ffi.release(font_map)
        folder = instance._folder
        instance._folder = None  # prevent upstream __del__ from hiding cleanup errors
        if folder is not None:
            shutil.rmtree(folder)  # fail closed on leaked/locked temporary font files
