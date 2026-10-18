"""Permanent offline controls for a completed witness, NOT a native-test substitute."""
import hashlib
import json
from pathlib import Path, PureWindowsPath
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DEPS = ROOT / 'docs/dependencies'
HEAD = 'fa68e2a93b0fc02eedf97fd228ecd85d407d5aa5'
WITNESS_SHA256 = '5396a1431461249a6c1b21832553cf1dc6ac0c96034e569728a99e7aec71abf0'


def _read(name):
    return json.loads((DEPS / name).read_text(encoding='utf-8'))


def _tree(node):
    return node.tag, sorted(node.attrib.items()), (node.text or '').strip(), tuple(_tree(c) for c in node)


def test_unicode_native_witness_binds_exact_completed_source_job_not_stock_preflight():
    proof = _read('pdf-unicode-bootstrap-proof.json')
    raw = (ROOT / proof['witness']['path']).read_bytes()
    assert len(raw) == proof['witness']['size']
    assert hashlib.sha256(raw).hexdigest() == proof['witness']['sha256'] == WITNESS_SHA256
    x = json.loads(raw)
    assert proof['run_id'] == 39175100427 and proof['head_sha'] == HEAD and proof['conclusion'] == 'success'
    assert len(proof['jobs']) == 2 and all(j['conclusion'] == 'success' and j['head_sha'] == HEAD for j in proof['jobs'])
    source_job = next(j for j in proof['jobs'] if j['name'] == 'unicode-consumer')
    preflight_job = next(j for j in proof['jobs'] if j['name'] == 'unicode-preflight')
    assert proof['job_id'] == source_job['id'] == 117816508451
    assert preflight_job['completed_at'] <= source_job['started_at']
    assert proof['artifact']['name'] == 'private-unicode-bootstrap-build-pdf-evidence-no-dlls'
    assert proof['artifact']['workflow_run']['head_sha'] == HEAD
    assert x['private_unicode_bootstrap_pdf'] == 'SUCCESS'
    assert x['compiled_from_noticed_archive'] and x['input_source_trees_unchanged_during_compilation']
    assert x['inline_change_date_notice_present_in_compiled_source']
    assert x['dll_count'] == len(x['dlls']) == 21
    prior = _read('pdf-noticed-archive-build-evidence.json')
    assert len(x['preferred_source_trees']) == 20 and x['preferred_source_trees'] == prior['preferred_source_trees']
    assert x['noticed_source_archive_sha256'] == proof['source_archive']['sha256'] == 'b1078a6bba74d86565b97694c8ac2afc6adf15c045a843cdbf55cb08f6226fc2'
    assert x['noticed_source_kit_receipt'] == prior['noticed_source_kit_receipt']
    assert x['noticed_source_kit_receipt']['new_native_build_from_this_envelope_proven'] is False
    assert proof['source_producer_run_id'] == 39165372821
    assert proof['source_artifact']['id'] == 12150501221
    assert proof['source_artifact']['digest'] == 'sha256:b4f8ddb1f51b62ef49f43442b6a5da15bdc9117ca6cdba161233bdd4d8707f0f'
    native = dict(x)
    for key in ['private_unicode_bootstrap_pdf', 'unicode_cases', 'native_audit_sha256_bound_to_candidate', 'ordinary_native_runtime_enabled', 'installed_user_acceptance', 'production_bootstrap_integration_proven']:
        native.pop(key)
    native['not_proven'] = prior['native_only_not_proven']
    assert hashlib.sha256((json.dumps(native, indent=2) + '\n').encode()).hexdigest() == x['native_audit_sha256_bound_to_candidate'] == proof['witness']['native_audit_sha256_bound_to_candidate']
    preflight = _read('pdf-unicode-bootstrap-preflight-proof.json')
    assert preflight['role'] == 'PINNED_STOCK_SDK_PREFLIGHT_NOT_SOURCE_PROVENANCE'
    assert preflight['source_build_proof'] is preflight['release_authorized'] is False
    assert preflight['run_id'] == proof['run_id'] and preflight['job_id'] == preflight_job['id']
    assert preflight['sdk_dll_count'] == 27  # explicitly NOT the 21 fresh source DLLs
    assert preflight['sdk_archive_sha256'] == 'ab1151f210b4e6bb7aa7a79e91a67e8ddb760094c107bfda55241b6aaefe7d53'
    assert preflight['artifact']['name'] == 'private-unicode-stock-sdk-preflight-no-dlls-not-source-proof'
    assert len(preflight['native_path_diagnostics']) == len(preflight['pdf_notices']) == 2
    for diag in preflight['native_path_diagnostics']:
        assert diag['windows_acp'] == 65001 and diag['python_utf8_mode'] == 1
        assert diag['paths']['unicode'] == {'added': [True, True], 'font_count': 2}


def test_unicode_restart_temp_fonts_modified_process_manifest_and_open_gates():
    proof = _read('pdf-unicode-bootstrap-proof.json')
    x = _read('pdf-unicode-bootstrap-evidence.json')
    assert proof['unicode_cases'] == x['unicode_cases']
    assert set(x['unicode_cases']) == {'first-process', 'restarted-process'}
    hashes = sorted(hashlib.sha256((ROOT / 'backend/app/assets/fonts' / f'Vazirmatn-{w}.ttf').read_bytes()).hexdigest() for w in ('Regular', 'Bold'))
    workers = []
    for name, case in x['unicode_cases'].items():
        w = case['worker']
        workers.append(w)
        assert w['isolated'] == w['utf8_mode'] == 1 and w['windows_active_code_page'] == 65001
        assert w['preferred_encoding'].lower() == w['weasyprint_path_encoding'].lower() == 'utf-8'
        assert w['development_dependencies_absent'] and w['ctypes_callbacks_verified']
        assert w['fontconfig_mode'] == 'EXPLICIT_UTF8_MEMORY_NO_SYSTEM_FONTS' and w['fontconfig_file'] is None
        assert w['pango_version_string'] == w['expected_pango_version_string'] == '1.58.0-vira-local-source'
        assert w['reused_state'] == (name == 'restarted-process')
        assert set(w['loaded_dlls']) == set(x['dlls']) and case['dll_count'] == len(w['loaded_dlls']) == 21
        app = PureWindowsPath(w['python']).parent.parent
        assert all(PureWindowsPath(p).parent == app / 'native/pdf/bin' for p in w['loaded_dlls'].values())
        assert all(not w[k].isascii() and ' ' in w[k] for k in ['python', 'unicode_temp', 'unicode_state', 'localappdata', 'working_directory'])
        assert {d['pages'] for d in case['documents'].values()} == {1, 4}
        for doc in case['documents'].values():
            assert {f['weight'] for f in doc['fonts']} == {400, 700}
            assert all(f['digits'] == '0123456789۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩' for f in doc['fonts'])
        for font_doc in w['font_documents'].values():
            assert font_doc['system_fonts'] == 0 and font_doc['font_temp_cleaned']
            assert font_doc['font_sha256'] == hashes
            assert PureWindowsPath(font_doc['font_folder']).parent == PureWindowsPath(w['unicode_temp'])
        manifest = w['process_manifest_bootstrap']
        assert manifest['private_only'] and not manifest['normal_payload_staging_changed']
        assert manifest['python_executable_is_unmodified_upstream_binary'] is manifest['release_or_redistribution_approval'] is False
        assert manifest['executable_sha256_before'] != manifest['executable_sha256_after']
        assert len(manifest['executable_sha256_after']) == len(manifest['tool']['sha256']) == 64
        assert manifest['tool']['name'] == 'mt.exe'
        before = ET.fromstring(manifest['original_manifest'])
        after = ET.fromstring(manifest['embedded_manifest'])
        acp = '{http://schemas.microsoft.com/SMI/2019/WindowsSettings}activeCodePage'
        assert not list(before.iter(acp))
        parent = list(after.iter('{urn:schemas-microsoft-com:asm.v3}windowsSettings'))
        node = list(after.iter(acp))
        assert len(parent) == len(node) == 1 and node[0].text == 'UTF-8'
        parent[0].remove(node[0])
        assert _tree(before) == _tree(after)  # retain trust/security/long-path settings
    assert all(workers[0][k] == workers[1][k] for k in ['python', 'unicode_state', 'unicode_temp', 'localappdata', 'fontconfig_xml_sha256', 'process_manifest_bootstrap'])
    assert proof['private_python_executable_pe_manifest_modified'] and not proof['unmodified_python_executable_claim']
    assert proof['release_authorized'] is proof['application_license_changed'] is proof['normal_renderer_default_changed'] is False
    assert proof['ordinary_native_runtime_enabled'] is proof['installed_user_acceptance'] is proof['production_bootstrap_integration_proven'] is False
    assert x['ordinary_native_runtime_enabled'] is x['installed_user_acceptance'] is x['production_bootstrap_integration_proven'] is False
    assert proof['licensed_build_files'] == 14
    policy = _read('pdf-runtime-license-policy.json')
    assert len(policy['open_gates']) == 6 and all(g.get('progress', {}).get('gate_closed', False) is False for g in policy['open_gates'])
