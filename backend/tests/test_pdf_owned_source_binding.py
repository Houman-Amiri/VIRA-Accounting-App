"""Synthetic source schema tests ONLY; writes tmp files, never native evidence."""
import importlib.util
import json
from pathlib import Path

import pytest

from . import test_pdf_source_http_binding as schema

synthetic_binding = schema.synthetic_binding
ROOT = Path(__file__).resolve().parents[2]


def setup_owned(synthetic_binding):
    audit, reports = synthetic_binding
    for name in ('first-process', 'restarted-process'):
        folder = reports/name
        parent = json.loads((folder/'launcher-proof.json').read_text())
        data = json.loads((folder/'http-bundled-proof.json').read_text())
        parent.update(target_mode='PRIVATE_APP_OWNED_HTTP', dll_count=21)
        worker = data['worker']
        worker.update(role='PRIVATE_APP_OWNED_SOURCE_HTTP_NOT_INSTALLED_ACCEPTANCE',
                      font_adapter_scope='APPLICATION_OWNED_FACTORY_POLICY_NOT_DEFAULT',
                      app_owned_dispatch={'mode':'PRIVATE_EXPLICIT_FONTCONFIG','renderer_module':'app.services.pdf_rendering',
                          'callables_unchanged':True,'qa_renderer_replacement_used':False,
                          'configuration_factory_supplied_by_qa':False,'cache_root_empty':True,
                          'diagnostics':'PASSIVE_PLAIN_VALUE_LOG_RECORDS_NOT_CONFIG_OBJECTS'})
        for i, record in enumerate(worker['font_documents']):
            record.update(cache_folder=f'SYNTHETIC-NOT-NATIVE/cache-{i}', cache_temp_cleaned=True)
        (folder/'launcher-proof.json').write_text(json.dumps(parent))
        (folder/'http-bundled-proof.json').write_text(json.dumps(data))
    return audit, reports


def module(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT/'scripts'))
    spec = importlib.util.spec_from_file_location('owned_bind_schema', ROOT/'scripts/pdf_owned_http_bind.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_synthetic_source_role_and_audit_projection_schema_not_new_proof(synthetic_binding, monkeypatch):
    audit, reports = setup_owned(synthetic_binding)
    x = module(monkeypatch).bind(reports, audit)
    assert x['role'] == 'PRIVATE_NOTICED_SOURCE_APP_OWNED_HTTP_NOT_DISTRIBUTION'
    assert x['source21_http_pair_proven'] and x['app_owned_dispatch_proven']
    assert not x['qa_renderer_replacement_used'] and not x['release_authorized']
    assert all(len(v['inventory']['dlls']) == 21 for v in x['cases'].values())


def test_synthetic_source_qa_replacement_cannot_be_relabelled_owned(synthetic_binding, monkeypatch):
    audit, reports = setup_owned(synthetic_binding)
    file = reports/'restarted-process/http-bundled-proof.json'
    x = json.loads(file.read_text())
    x['worker']['app_owned_dispatch']['qa_renderer_replacement_used'] = True
    file.write_text(json.dumps(x))
    with pytest.raises(ValueError, match='Application-owned process/dispatch'):
        module(monkeypatch).bind(reports, audit)
