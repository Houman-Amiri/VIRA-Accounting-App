"""Negative/ownership controls, not substitutes for real Windows Unicode PDF proof."""
from pathlib import Path
from types import SimpleNamespace
from xml.etree.ElementTree import fromstring

import pytest

from app.services import pdf_fontconfig as adapter


@pytest.fixture()
def native(monkeypatch):
    calls = []
    config, font_map = object(), object()
    class Container:
        def __init__(self):
            raise AssertionError('Default getenv-based initializer must not run')
    fc = SimpleNamespace(
        FcConfigCreate=lambda: config,
        FcConfigParseAndLoadFromMemory=lambda *args: calls.append(('parse', args[1])) or True,
        FcConfigBuildFonts=lambda _: True,
        FcConfigGetFonts=lambda *_: SimpleNamespace(nfont=0), FcSetSystem=0,
        FcConfigDestroy=lambda ptr: calls.append(('destroy', ptr)),
    )
    ffi = SimpleNamespace(NULL=None, gc=lambda ptr, _: ptr, cast=lambda _, ptr: ptr,
                          release=lambda ptr: calls.append(('release', ptr)))
    pango = SimpleNamespace(pango_ft2_font_map_new=lambda: font_map,
                            pango_fc_font_map_set_config=lambda m, c: calls.append(('attach', m, c)))
    obj = SimpleNamespace(ffi=ffi, fontconfig=fc, pangoft2=pango,
                          gobject=SimpleNamespace(g_object_unref=lambda _: None), FontConfiguration=Container)
    monkeypatch.setattr(adapter, '_bindings', lambda: obj)
    return obj, calls, config, font_map


def test_xml_has_only_explicit_utf8_cache_and_no_includes(tmp_path):
    cache = tmp_path / 'حافظه & مسیر با فاصله'
    cache.mkdir()
    data = adapter.configuration_xml(cache)
    root = fromstring(data)
    assert root.tag == 'fontconfig' and [c.tag for c in root] == ['reset-dirs', 'cachedir']
    assert root.find('cachedir').text == cache.resolve().as_posix()
    assert b'&amp;' in data and 'حافظه'.encode() in data


def test_cache_must_exist_and_not_be_a_symlink(tmp_path):
    with pytest.raises(ValueError):
        adapter.configuration_xml(tmp_path / 'missing')
    link = tmp_path / 'alias'
    link.symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        adapter.configuration_xml(link)


def test_native_config_owns_exact_refs_and_cleans_unicode_fonts(native, tmp_path):
    _, calls, config, font_map = native
    folder = tmp_path / 'قلم موقت'
    folder.mkdir()
    (folder / 'font').write_bytes(b'fake, not native evidence')
    with adapter.private_font_configuration(tmp_path) as obj:
        assert obj._config is config and obj.font_map is font_map
        obj._folder = folder
        obj.strut_layouts['layout'] = 'cached'
        assert calls[-1] == ('destroy', config)  # Pango owns the remaining reference
    assert calls[-1] == ('release', font_map)
    assert sum(c[0] == 'destroy' for c in calls) == sum(c[0] == 'release' for c in calls) == 1
    assert not folder.exists() and obj._folder is None and not obj.strut_layouts
    assert not hasattr(obj, 'font_map') and not hasattr(obj, '_config')


@pytest.mark.parametrize('fault', ['allocate', 'parse', 'build', 'system-fonts', 'null-fontset', 'map', 'gc', 'attach'])
def test_no_silent_system_or_default_fallback(native, tmp_path, fault):
    bindings, calls, _, _ = native
    if fault == 'allocate':
        bindings.fontconfig.FcConfigCreate = lambda: None
    if fault == 'parse':
        bindings.fontconfig.FcConfigParseAndLoadFromMemory = lambda *_: False
    if fault == 'build':
        bindings.fontconfig.FcConfigBuildFonts = lambda *_: False
    if fault in ('system-fonts', 'null-fontset'):
        bindings.fontconfig.FcConfigGetFonts = lambda *_: None if fault == 'null-fontset' else SimpleNamespace(nfont=1)
    if fault == 'map':
        bindings.pangoft2.pango_ft2_font_map_new = lambda: None
    def fail(*_):
        raise RuntimeError('native ownership failure')
    if fault == 'gc':
        bindings.ffi.gc = fail
        bindings.gobject.g_object_unref = lambda ptr: calls.append(('unref-raw', ptr))
    if fault == 'attach':
        bindings.pangoft2.pango_fc_font_map_set_config = fail
    with pytest.raises(RuntimeError), adapter.private_font_configuration(tmp_path):
        pytest.fail('A broken config must not yield a usable renderer')
    assert sum(c[0] == 'destroy' for c in calls) == (0 if fault == 'allocate' else 1)


def test_body_exception_still_releases_config(native, tmp_path):
    _, calls, _, _ = native
    with pytest.raises(RuntimeError, match='render failed'), adapter.private_font_configuration(tmp_path):
        raise RuntimeError('render failed')
    assert calls[-1][0] == 'release'


def test_cleanup_failure_is_not_hidden(native, tmp_path, monkeypatch):
    def denied(_):
        raise PermissionError('locked font')
    monkeypatch.setattr(adapter.shutil, 'rmtree', denied)
    with pytest.raises(PermissionError, match='locked font'), adapter.private_font_configuration(tmp_path) as obj:
        obj._folder = tmp_path / 'folder'
    assert obj._folder is None


def test_explicit_injection_does_not_enable_the_adapter_in_normal_rendering():
    root = Path(__file__).resolve().parents[2]
    text = (root / 'backend/app/services/pdf.py').read_text(encoding='utf-8')
    assert 'FontConfiguration() if font_configuration is None else font_configuration' in text
    assert 'pdf_fontconfig' not in text


def test_unreviewed_weasyprint_version_fails_before_native_import(monkeypatch):
    monkeypatch.setattr(adapter, 'version', lambda _: '71.0')
    with pytest.raises(RuntimeError, match='reviewed WeasyPrint 70.0'):
        adapter._bindings()


def test_windows_bootstrap_requires_explicit_utf8_before_native_import(monkeypatch):
    monkeypatch.setattr(adapter, 'version', lambda _: '70.0')
    monkeypatch.setattr(adapter, 'sys', SimpleNamespace(platform='win32', flags=SimpleNamespace(utf8_mode=0)))
    with pytest.raises(RuntimeError, match='CPython -X utf8'):
        adapter._bindings()
