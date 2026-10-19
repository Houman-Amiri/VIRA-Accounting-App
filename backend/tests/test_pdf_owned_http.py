"""Offline guards/synthetic schema volumes; NEVER fresh native or HTTP proof."""
import importlib.util
import json
import logging
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import pdf, pdf_fontconfig
from app.services.pdf_rendering import PdfRenderer, PrivatePdfPolicy

ROOT = Path(__file__).resolve().parents[2]


def script(name, monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name+'.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_owned_launcher_requires_explicit_http_before_reading_files(tmp_path, monkeypatch):
    launcher = script('pdf_private_launcher', monkeypatch)
    with pytest.raises(ValueError, match='requires explicit private HTTP'):
        launcher.validate_payload(tmp_path, 'a'*64, 'b'*64, app_owned=True)


def test_application_emits_plain_value_events_after_both_cleanups(tmp_path, monkeypatch, caplog):
    @contextmanager
    def config(cache):
        yield SimpleNamespace()
    monkeypatch.setattr(pdf_fontconfig, 'private_font_configuration', config)
    original = lambda *args, **kwargs: b'%PDF-FAKE-NOT-NATIVE'  # noqa: E731
    monkeypatch.setattr(pdf, 'render_pdf', original)
    # Alembic fileConfig can disable loggers created during test collection.
    monkeypatch.setattr(logging.getLogger('app.services.pdf_rendering'), 'disabled', False)
    caplog.set_level(logging.INFO, logger='app.services.pdf_rendering')
    renderer = PdfRenderer(PrivatePdfPolicy(tmp_path/'cache'))
    assert renderer('proforma.html', {}) == b'%PDF-FAKE-NOT-NATIVE'
    assert pdf.render_pdf is original
    events = [r.pdf_document for r in caplog.records if hasattr(r, 'pdf_document')]
    assert [e['event'] for e in events] == ['started', 'completed']
    assert events[0]['id'] == events[1]['id']
    assert events[1]['cache_temp_cleaned'] and not Path(events[1]['cache_folder']).exists()
    assert events[1]['font_folder'] is None and events[1]['system_fonts'] is None  # fake, not native
    json.dumps(events)  # no C pointer/config/callback in log records


def test_failed_events_balance_interrupt_without_success(tmp_path, monkeypatch, caplog):
    @contextmanager
    def config(cache):
        yield object()
    def interrupted(*args, **kwargs):
        raise KeyboardInterrupt('synthetic')
    monkeypatch.setattr(pdf_fontconfig, 'private_font_configuration', config)
    monkeypatch.setattr(pdf, 'render_pdf', interrupted)
    # Alembic fileConfig can disable loggers created during test collection.
    monkeypatch.setattr(logging.getLogger('app.services.pdf_rendering'), 'disabled', False)
    caplog.set_level(logging.INFO, logger='app.services.pdf_rendering')
    with pytest.raises(KeyboardInterrupt):
        PdfRenderer(PrivatePdfPolicy(tmp_path/'cache'))('proforma.html', {})
    events = [r.pdf_document for r in caplog.records if hasattr(r, 'pdf_document')]
    assert [e['event'] for e in events] == ['started', 'failed']
    assert not list((tmp_path/'cache').iterdir())


def test_passive_observer_never_replaces_renderer_and_rejects_incomplete_events(monkeypatch, tmp_path):
    worker = script('pdf_private_http_probe', monkeypatch)
    before = pdf.render_pdf
    observer = worker.OwnedFontObserver(tmp_path, tmp_path, tmp_path)
    for event in [{'event':'started','id':'one'}, {'event':'failed','id':'one'}]:
        record = logging.makeLogRecord({'pdf_document':event})
        observer.handle(record)
    assert observer.peak == 1 and observer.active == 0 and not observer.active_ids and observer.errors
    assert pdf.render_pdf is before
    # verify fails before touching font assets because the lifecycle is incomplete.
    with pytest.raises((ValueError, FileNotFoundError)):
        observer.verify()


@pytest.fixture()
def synthetic_owned(tmp_path):
    x = json.loads((ROOT/'docs/dependencies/pdf-private-http-evidence.json').read_text())
    for name, case in x['cases'].items():
        p, c = case['launcher'], case['http_pdf']
        p['target_mode'] = 'PRIVATE_APP_OWNED_HTTP'
        w = c['worker']
        w['role'] = 'PRIVATE_APP_OWNED_SDK_HTTP_NOT_INSTALLED_ACCEPTANCE'
        w['font_adapter_scope'] = 'APPLICATION_OWNED_FACTORY_POLICY_NOT_DEFAULT'
        w['app_owned_dispatch'] = {'mode':'PRIVATE_EXPLICIT_FONTCONFIG', 'renderer_module':'app.services.pdf_rendering',
          'callables_unchanged':True, 'qa_renderer_replacement_used':False, 'configuration_factory_supplied_by_qa':False,
          'cache_root_empty':True,'diagnostics':'PASSIVE_PLAIN_VALUE_LOG_RECORDS_NOT_CONFIG_OBJECTS'}
        for i, record in enumerate(w['font_documents']):
            record.update(cache_folder=f'SYNTHETIC-NOT-NATIVE/cache-{i}', cache_temp_cleaned=True)
        folder = tmp_path/name
        folder.mkdir()
        for file, data in [('launcher-proof.json',p), ('http-bundled-proof.json',c)]:
            (folder/file).write_text(json.dumps(data))
    (tmp_path/'negative-controls.json').write_text(json.dumps(x['negative_controls']))
    return tmp_path


def test_synthetic_owned_binding_is_sdk_only_not_compilation(synthetic_owned, monkeypatch):
    x = script('pdf_owned_http_bind', monkeypatch).bind(synthetic_owned)
    assert x['new_source_build_proven'] is x['source21_http_pair_proven'] is False
    assert x['app_owned_dispatch_proven'] and not x['qa_renderer_replacement_used']
    assert x['installed_user_acceptance'] is x['release_authorized'] is False


@pytest.mark.parametrize('fault', ['target','replacement','config-injection','callables','cache','pid','hash','documents','negative'])
def test_synthetic_owned_binding_rejects_bad_contract(synthetic_owned, monkeypatch, fault):
    folder = synthetic_owned/'restarted-process'
    p = json.loads((folder/'launcher-proof.json').read_text())
    c = json.loads((folder/'http-bundled-proof.json').read_text())
    if fault == 'target':
        p['target_mode'] = 'PRIVATE_HTTP_QA'
    if fault == 'replacement':
        c['worker']['app_owned_dispatch']['qa_renderer_replacement_used'] = True
    if fault == 'config-injection':
        c['worker']['app_owned_dispatch']['configuration_factory_supplied_by_qa'] = True
    if fault == 'callables':
        c['worker']['app_owned_dispatch']['callables_unchanged'] = False
    if fault == 'cache':
        c['worker']['font_documents'][0]['cache_temp_cleaned'] = False
    if fault == 'pid':
        p['pid'] = json.loads((synthetic_owned/'first-process/launcher-proof.json').read_text())['pid']
    if fault == 'hash':
        next(iter(c['documents'].values()))['sha256'] = '0'*64
    if fault == 'documents':
        c['documents'].pop(next(iter(c['documents'])))
    if fault == 'negative':
        (synthetic_owned/'negative-controls.json').write_text('{}')
    (folder/'launcher-proof.json').write_text(json.dumps(p))
    (folder/'http-bundled-proof.json').write_text(json.dumps(c))
    with pytest.raises(ValueError):
        script('pdf_owned_http_bind', monkeypatch).bind(synthetic_owned)


def test_workflow_sdk_and_source_lanes_remain_separate_and_source_cold_build_precedes_owned():
    import yaml
    sdk = yaml.safe_load((ROOT/'.github/workflows/pdf-app-owned-http.yml').read_text())
    src = yaml.safe_load((ROOT/'.github/workflows/pdf-source-http.yml').read_text())
    sdktext = json.dumps(sdk)
    assert '-HttpProof -AppOwnedFonts' in sdktext and '--source-audit ' not in sdktext
    steps = src['jobs']['source-http-consumer']['steps']
    build = next(i for i,v in enumerate(steps) if v.get('name','').startswith('Compile all'))
    owned = next(i for i,v in enumerate(steps) if '-HttpProof -AppOwnedFonts -SourceAudit' in v.get('run',''))
    assert build < owned
    assert any('after application-owned' in v.get('name','') for v in steps[owned+1:])
    assert len([v for v in steps if v.get('name','').startswith('App-owned source evidence group')]) == 4
    assert 'reports/source-owned-http/' in steps[-1]['with']['path']


def test_fingerprint_checks_app_source_through_contextmanager_wrapper(monkeypatch):
    worker = script('pdf_private_http_probe', monkeypatch)
    values = worker.owned_fingerprint(ROOT/'backend')
    assert values['render_pdf'] is pdf.render_pdf
    assert values['private_font_configuration'] is pdf_fontconfig.private_font_configuration
    monkeypatch.setattr(pdf, 'render_pdf', lambda *a, **k: b'FAKE')
    with pytest.raises(ValueError, match='Foreign/replaced'):
        worker.owned_fingerprint(ROOT/'backend')


def test_passive_active_count_matches_shared_worker_postcondition(monkeypatch, tmp_path):
    worker = script('pdf_private_http_probe', monkeypatch)
    observer = worker.OwnedFontObserver(tmp_path, tmp_path, tmp_path)
    assert observer.active == 0
    observer.handle(logging.makeLogRecord({'pdf_document': {'event':'started','id':'doc'}}))
    assert observer.active == 1
    observer.handle(logging.makeLogRecord({'pdf_document': {'event':'completed','id':'doc'}}))
    assert observer.active == 0
