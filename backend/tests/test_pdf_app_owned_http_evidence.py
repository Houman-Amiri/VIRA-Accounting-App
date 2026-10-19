"""Recorded real Windows app-owned HTTP; no relabelled historical native proof."""
import hashlib
import json
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
DEP = ROOT/'docs/dependencies'


def verify_recorded(kind, source, run):
    p = json.loads((DEP/f'pdf-app-owned-{kind}-http-proof.json').read_text())
    raw = (ROOT/p['witness']['path']).read_bytes()
    assert len(raw) == p['witness']['bytes'] and hashlib.sha256(raw).hexdigest() == p['witness']['sha256']
    x = json.loads(raw)
    assert p['run_id'] == run and p['head_sha'] == '66e3b8d575be879b574ec1c0c3328e74b23b7ce2'
    assert p['conclusion'] == 'success' and all(j['conclusion'] == 'success' for j in p['jobs'])
    assert p['artifact']['workflow_run']['head_sha'] == p['head_sha']
    assert p['witness']['authenticated_annotation_parts'] <= 32
    assert x['role'] == ('PRIVATE_NOTICED_SOURCE_APP_OWNED_HTTP_NOT_DISTRIBUTION' if source else 'PRIVATE_SDK_APP_OWNED_HTTP_NOT_SOURCE_OR_INSTALLED_PROOF')
    assert x['app_owned_dispatch_proven'] is x['http_app_startup_proven'] is True
    assert x['new_source_build_proven'] is x['source21_http_pair_proven'] is source
    for flag in ('qa_renderer_replacement_used', 'configuration_factory_supplied_by_qa', 'font_adapter_is_production_default', 'ordinary_launcher_enabled', 'installed_user_acceptance', 'release_authorized'):
        assert x[flag] is False
    count = 21 if source else 27
    first, again = [x['cases'][v] for v in ('first-process', 'restarted-process')]
    assert first['launcher']['pid'] != again['launcher']['pid']
    assert first['launcher']['inventory_sha256'] == again['launcher']['inventory_sha256']
    assert first['http_pdf']['worker']['database'] == again['http_pdf']['worker']['database']
    assert first['http_pdf']['worker']['http']['fixture_ids'] == again['http_pdf']['worker']['http']['fixture_ids']
    hashes = sorted(hashlib.sha256((ROOT/'backend/app/assets/fonts'/f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
    for name, value in x['cases'].items():
        parent, child = value['launcher'], value['http_pdf']['worker']
        assert parent['pid'] == child['pid'] and parent['target_mode'] == 'PRIVATE_APP_OWNED_HTTP'
        assert parent['no_site'] == parent['isolated'] == parent['utf8_mode'] == 1
        assert parent['windows_acp'] == 65001 and parent['app_and_weasyprint_absent_before_entry']
        assert parent['dll_count'] == value['http_pdf']['dll_count'] == len(child['loaded_dlls']) == count
        app = PureWindowsPath(child['python']).parent.parent
        assert all(PureWindowsPath(v).parent == app/'native/pdf/bin' for v in child['loaded_dlls'].values())
        owned = child['app_owned_dispatch']
        assert owned['mode'] == 'PRIVATE_EXPLICIT_FONTCONFIG' and owned['renderer_module'] == 'app.services.pdf_rendering'
        assert owned['callables_unchanged'] and owned['cache_root_empty']
        assert not owned['qa_renderer_replacement_used'] and not owned['configuration_factory_supplied_by_qa']
        assert owned['diagnostics'] == 'PASSIVE_PLAIN_VALUE_LOG_RECORDS_NOT_CONFIG_OBJECTS'
        assert child['reused_state'] == (name == 'restarted-process')
        http = child['http']
        assert http['transport'] == 'REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT'
        assert http['parallel_http_requests'] == 2 and http['peak_concurrent_documents'] == 1
        assert http['graceful_shutdown'] and http['compiled_spa_served'] and http['route_context_from_sqlite']
        assert http['unauthorized_pdf_rejected'] and http['wrong_login_rejected'] and http['missing_csrf_rejected']
        assert len(child['font_documents']) == len(value['http_pdf']['documents']) == 4
        assert len({v['font_folder'] for v in child['font_documents']}) == len({v['cache_folder'] for v in child['font_documents']}) == 4
        assert all(v['font_sha256'] == hashes and v['font_temp_cleaned'] and v['cache_temp_cleaned'] and v['system_fonts'] == 0 for v in child['font_documents'])
        for filename, doc in value['http_pdf']['documents'].items():
            assert doc['sha256'] == http['documents'][filename]['sha256'] and doc['bytes'] == http['documents'][filename]['bytes']
            assert doc['pages'] == (4 if 'multi' in filename else 1)
            assert {f['weight'] for f in doc['fonts']} == {400, 700}
            assert all(f['digits'] == ('0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩' if f['weight'] == 400 else '۰۱۲۳۴۵۶۷۸۹') for f in doc['fonts'])
    assert len(x['negative_controls']) == 3 and all(v['rejected'] and v['exit_code'] != 0 for v in x['negative_controls'].values())
    if source:
        audit = x['native_audit']
        assert hashlib.sha256((json.dumps(audit, indent=2)+'\n').encode()).hexdigest() == x['native_audit_sha256'] == p['native_audit_sha256']
        assert len(audit['preferred_source_trees']) == 20 and len(audit['dlls']) == 21
        assert audit['compiled_from_noticed_archive'] and audit['inline_change_date_notice_present_in_compiled_source']
        assert audit['actual_pango_version_string'] == '1.58.0-vira-local-source'
    else:
        assert all(v['http_pdf']['worker']['pango_version'] == '1.58.2' for v in x['cases'].values())
    for oldfile in ('pdf-source-http-proof.json', 'pdf-private-http-proof.json', 'pdf-unicode-bootstrap-proof.json'):
        old = json.loads((DEP/oldfile).read_text())
        assert hashlib.sha256((ROOT/old['witness']['path']).read_bytes()).hexdigest() == old['witness']['sha256']
        assert old['run_id'] != run
    failed = json.loads((DEP/'pdf-app-owned-http-worker-failure.json').read_text())
    assert failed['run_id'] == 39242791845 and failed['conclusion'] == 'failure'
    policy = json.loads((DEP/'pdf-runtime-license-policy.json').read_text())
    review = json.loads((DEP/'pdf-runtime-license-review.json').read_text())
    assert len(policy['open_gates']) == 6 and policy['open_gates'] == review['open_gates']
    assert all(not g['progress']['gate_closed'] for g in policy['open_gates'])


def test_real_recorded_sdk_app_owned_http_not_source_provenance():
    verify_recorded('sdk', False, 39243690293)


def test_real_recorded_fresh_source_app_owned_http_not_ordinary_startup():
    verify_recorded('source', True, 39243690330)
