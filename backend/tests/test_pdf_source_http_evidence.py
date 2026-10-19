"""Authenticated fresh Windows witness; historical SDK/source evidence stays separate."""
import hashlib
import json
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parents[2]
DEP = ROOT / 'docs/dependencies'


def recorded():
    proof = json.loads((DEP / 'pdf-source-http-proof.json').read_text())
    raw = (ROOT / proof['witness']['path']).read_bytes()
    assert len(raw) == proof['witness']['bytes']
    assert hashlib.sha256(raw).hexdigest() == proof['witness']['sha256']
    return proof, json.loads(raw)


def test_fresh_recorded_source_compile_and_http_have_authenticated_shared_native_audit(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    from pdf_private_launcher import (
        SOURCE_ARCHIVE,
        SOURCE_FILE,
        SOURCE_MANIFEST,
        validate_source_inventory,
    )
    p, x = recorded()
    assert p['run_id'] == 39226693623 and p['source_job_id'] == 117975682474
    assert p['head_sha'] == 'b04440eaef218a3f7a2a7942231b21e7443babcb'
    assert p['conclusion'] == 'success' and len(p['jobs']) == 2
    assert all(j['conclusion'] == 'success' for j in p['jobs'])
    assert p['artifact']['workflow_run']['head_sha'] == p['head_sha']
    assert 0 < p['witness']['authenticated_annotation_parts'] <= 32
    assert x['role'] == 'PRIVATE_NOTICED_SOURCE_BUILD_AND_REAL_HTTP_NOT_DISTRIBUTION'
    assert x['source21_http_pair_proven'] is x['new_source_build_proven'] is x['http_app_startup_proven'] is True
    audit = x['native_audit']
    assert hashlib.sha256((json.dumps(audit, indent=2)+'\n').encode()).hexdigest() == x['native_audit_sha256'] == p['native_audit_sha256']
    assert audit['noticed_source_archive_sha256'] == SOURCE_ARCHIVE
    assert audit['noticed_source_file_sha256'] == SOURCE_FILE
    assert audit['noticed_source_kit_receipt']['modified_kit_manifest_sha256'] == SOURCE_MANIFEST
    assert audit['actual_pango_version_string'] == '1.58.0-vira-local-source'
    assert len(audit['preferred_source_trees']) == 20 and len(audit['dlls']) == 21
    assert x['inventory_representation'] == 'VALIDATED_BINDING_PROJECTION_FULL_BYTE_HASHED_INVENTORY_IN_ARTIFACT'
    for case in x['source_http_cases'].values():
        validate_source_inventory(case['inventory'], audit, x['native_audit_sha256'])
        parent, child = case['launcher'], case['http_pdf']['worker']
        assert parent['pid'] == child['pid']
        assert parent['source_audit_bound'] and child['source_audit_bound']
        assert parent['source_audit_sha256'] == child['source_audit_sha256'] == p['native_audit_sha256']
        assert parent['dll_count'] == len(child['loaded_dlls']) == 21
        app = PureWindowsPath(child['python']).parent.parent
        assert all(PureWindowsPath(path).parent == app/'native/pdf/bin' for path in child['loaded_dlls'].values())
        assert parent['libffi'] == child['loaded_dlls']['ffi-8.dll']
    # The failed transport is retained as FAILED, not silently promoted to this run.
    failed = json.loads((DEP / 'pdf-source-http-evidence-transport-failure.json').read_text())
    assert failed['run_id'] == 39220310210 and failed['conclusion'] == 'failure'
    steps = {s['name']: s['conclusion'] for s in failed['source_job']['steps']}
    assert steps['Fresh no-site source HTTP launcher, real route PDFs and restart'] == 'success'
    assert steps['Source HTTP evidence group 0'] == 'failure'


def test_recorded_source_route_fonts_restart_and_open_gates_are_not_sdk_or_installed_acceptance():
    p, x = recorded()
    cases = x['source_http_cases']
    first, again = [cases[n] for n in ('first-process', 'restarted-process')]
    assert first['launcher']['pid'] != again['launcher']['pid']
    assert first['launcher']['inventory_sha256'] == again['launcher']['inventory_sha256']
    assert first['http_pdf']['worker']['database'] == again['http_pdf']['worker']['database']
    assert first['http_pdf']['worker']['http']['fixture_ids'] == again['http_pdf']['worker']['http']['fixture_ids']
    hashes = sorted(hashlib.sha256((ROOT/'backend/app/assets/fonts'/f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
    for name, case in cases.items():
        parent, child = case['launcher'], case['http_pdf']['worker']
        assert parent['no_site'] == parent['isolated'] == parent['utf8_mode'] == 1
        assert parent['windows_acp'] == 65001 and parent['app_and_weasyprint_absent_before_entry']
        assert child['reused_state'] == (name == 'restarted-process')
        assert child['pango_version'] == '1.58.0-vira-local-source'
        http = child['http']
        assert http['transport'] == 'REAL_TCP_LOOPBACK_NOT_ASGI_TRANSPORT'
        assert http['parallel_http_requests'] == 2 and http['peak_concurrent_documents'] == 1
        assert http['lifespan_started'] and http['graceful_shutdown'] and http['compiled_spa_served']
        assert http['unauthorized_pdf_rejected'] and http['wrong_login_rejected'] and http['missing_csrf_rejected']
        assert len(case['http_pdf']['documents']) == len(child['font_documents']) == 4
        for name, doc in case['http_pdf']['documents'].items():
            assert doc['sha256'] == http['documents'][name]['sha256']
            assert doc['bytes'] == http['documents'][name]['bytes']
            assert doc['pages'] == (4 if 'multi' in name else 1)
            assert {f['weight'] for f in doc['fonts']} == {400, 700}
            for font in doc['fonts']:
                assert font['digits'] == ('0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩' if font['weight'] == 400 else '۰۱۲۳۴۵۶۷۸۹')
        assert all(d['font_temp_cleaned'] and d['system_fonts'] == 0 and d['font_sha256'] == hashes for d in child['font_documents'])
    assert len(x['negative_controls']) == 3 and all(v['rejected'] and v['exit_code'] != 0 for v in x['negative_controls'].values())
    for flag in ('stock_sdk_used_in_source_job', 'font_adapter_is_production_default', 'ordinary_launcher_enabled', 'installed_user_acceptance', 'release_authorized'):
        assert x[flag] is False
    for filename in ('pdf-private-http-proof.json', 'pdf-unicode-bootstrap-proof.json'):
        old = json.loads((DEP / filename).read_text())
        assert hashlib.sha256((ROOT / old['witness']['path']).read_bytes()).hexdigest() == old['witness']['sha256']
        assert old['run_id'] != p['run_id']
    policy = json.loads((DEP / 'pdf-runtime-license-policy.json').read_text())
    assert len(policy['open_gates']) == 6
    assert all(g['progress']['gate_closed'] is False for g in policy['open_gates'])
