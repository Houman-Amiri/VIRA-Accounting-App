"""Full modified archive correspondence; synthetic security tests are not build proof."""
from __future__ import annotations

import copy
import hashlib
import importlib
import json
import os
import stat
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def tree(items):
    h = hashlib.sha256()
    for name, data, mode in sorted(items):
        kind = b'symlink' if stat.S_ISLNK(mode) else b'file'
        h.update(name.encode() + b'\0' + kind + b'\0' + sha(data).encode() + b'\n')
    return {'source_entries': len(items), 'tree_sha256': h.hexdigest()}


@pytest.fixture()
def sample(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    tool = importlib.import_module('pdf_source_kit')
    base = tmp_path / 'base'
    (base / 'evidence').mkdir(parents=True)
    old = b'/* upstream license */\nreturn PANGO_VERSION_STRING;\n'
    new = old.replace(b'return PANGO_VERSION_STRING;', b'return PANGO_VERSION_STRING "-vira-local-source";')
    items = [('v1.clean/pango/pango-utils.c', old, stat.S_IFREG | 0o644),
             ('v1.clean/LICENSES/L.txt', b'upstream terms', stat.S_IFREG | 0o644),
             ('v1.clean/COPYING', b'LICENSES/L.txt', stat.S_IFLNK | 0o777),
             ('v1.clean/run.sh', b'#!/bin/sh\n', stat.S_IFREG | 0o755)]
    with zipfile.ZipFile(base / 'corresponding-source.zip', 'w') as z:
        z.comment = b'original archive comment'
        for name, data, mode in items:
            info = zipfile.ZipInfo('sources/pango/' + name, (2024, 2, 21, 16, 35, 54))
            info.create_system = 3
            info.external_attr = mode << 16
            info.comment = b'original member comment'
            z.writestr(info, data)
    original_sha = sha((base / 'corresponding-source.zip').read_bytes())
    monkeypatch.setattr(tool, 'SOURCE_SHA', original_sha)
    trees = {'pango': tree([(n, new if n.endswith('pango-utils.c') else d, m) for n, d, m in items]),
             **{f'pkg{i}': tree([]) for i in range(19)}}
    inventory = {'source_packages': {n: {'patched_source_files': t['source_entries'],
                 'patched_source_tree_sha256': tree(items)['tree_sha256'] if n == 'pango' else t['tree_sha256']}
                 for n, t in trees.items()}}
    (base / 'evidence/pdf-runtime-win64-source-inventory.json').write_text(json.dumps(inventory))
    base_files = {p.relative_to(base).as_posix(): {'sha256': sha(p.read_bytes()), 'size': p.stat().st_size}
                  for p in base.rglob('*') if p.is_file()}
    (base / 'kit-manifest.json').write_text(json.dumps({'files': base_files}))
    base_sha = sha((base / 'kit-manifest.json').read_bytes())
    def verify_base(path, expected):
        assert expected == base_sha
        return {'kit_manifest_sha256': base_sha, 'licensed_files': 14}
    monkeypatch.setattr(tool, 'verify', verify_base)
    proof = {'distribution_status': tool.BLOCKED, 'native_compilation': 'SUCCESS',
             'local_preferred_source_replay': 'SUCCESS', 'private_local_source_payload_pdf': 'SUCCESS',
             'changed_packages': ['pango'], 'dll_count': 21, 'dlls': {str(i): {} for i in range(21)},
             'actual_pango_version_string': '1.58.0-vira-local-source',
             'input_source_trees_unchanged_during_compilation': True, 'original_archive_modified': False,
             'kit_receipt': {'source_archive_sha256': original_sha}, 'preferred_source_trees': trees,
             'explicit_edit': {'file': 'v1.clean/pango/pango-utils.c', 'package': 'pango',
                               'modified_source_file': new.decode(), 'before_sha256': sha(old), 'after_sha256': sha(new)}}
    witness_dir = tmp_path / 'audit'
    witness_dir.mkdir()
    witness = witness_dir / 'witness.json'
    witness.write_text(json.dumps(proof))
    return tool, base, base_sha, witness, proof, tmp_path / 'modified'


def build(sample):
    tool, base, digest, witness, _, out = sample
    return tool.build_modified(base, digest, witness, sha(witness.read_bytes()), '2026-10-18', out)


def rehash(tool, out):
    p = out / tool.MODIFIED_MANIFEST
    manifest = json.loads(p.read_text())
    for name in manifest['files']:
        data = (out / name).read_bytes()
        manifest['files'][name] = {'sha256': sha(data), 'size': len(data)}
    p.write_text(json.dumps(manifest))
    return sha(p.read_bytes())


def test_full_modified_archive_is_separate_preserves_sources_and_never_grants_clearance(sample):
    tool, base, _, _, _, out = sample
    original = (base / 'corresponding-source.zip').read_bytes()
    result = build(sample)
    assert (base / 'corresponding-source.zip').read_bytes() == original
    assert (out / 'original-kit/corresponding-source.zip').read_bytes() == original
    assert result['verified_sources']['packages'] == 20
    assert result['verified_sources']['source_entries'] == 4
    assert result['verified_sources']['source_symlinks'] == 1
    assert result['modified_archive_sha256'] != result['original_archive_sha256']
    assert result['new_modified_source_archive_prepared'] is True
    assert result['legal_notice_completeness_approved'] is False
    assert result['modified_build_is_distribution_candidate'] is False
    assert result['new_native_build_from_this_envelope_proven'] is False
    assert result['recipient_source_delivery'] is False
    assert result['distribution_status'] == tool.BLOCKED
    assert b'inline VIRA change/date notice' in (out / 'VIRA-MODIFICATIONS.txt').read_bytes()
    assert tool.verify_modified(out, sha((out / tool.MODIFIED_MANIFEST).read_bytes())) == result


def test_existing_output_and_nested_inputs_rejected_without_user_data_loss(sample):
    tool, base, digest, witness, _, out = sample
    out.mkdir()
    (out / 'user-data').write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        build(sample)
    assert (out / 'user-data').read_bytes() == b'keep'
    for nested in [base / 'new', witness.parent / 'new']:
        with pytest.raises(ValueError, match='outside'):
            tool.build_modified(base, digest, witness, sha(witness.read_bytes()), '2026-10-18', nested)
        assert not nested.exists()


@pytest.mark.parametrize('field,value', [
    ('distribution_status', 'APPROVED'), ('native_compilation', 'FAILURE'),
    ('local_preferred_source_replay', 'PENDING'), ('private_local_source_payload_pdf', 'PENDING'),
    ('changed_packages', []), ('dll_count', 27), ('actual_pango_version_string', '1.58.0'),
    ('input_source_trees_unchanged_during_compilation', False), ('original_archive_modified', True),
])
def test_failed_or_unwitnessed_build_never_creates_review_bundle(sample, field, value):
    _, _, _, witness, proof, out = sample
    proof[field] = value
    witness.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match='witness required'):
        build(sample)
    assert not out.exists()


def test_external_witness_digest_is_not_self_authentication(sample):
    tool, base, digest, witness, _, out = sample
    with pytest.raises(ValueError, match='External native witness'):
        tool.build_modified(base, digest, witness, '0' * 64, '2026-10-18', out)
    assert not out.exists()


@pytest.mark.parametrize('date', ['20261018', '2026-02-30', 'yesterday'])
def test_modification_notice_requires_real_canonical_date(sample, date):
    tool, base, digest, witness, _, out = sample
    with pytest.raises(ValueError):
        tool.build_modified(base, digest, witness, sha(witness.read_bytes()), date, out)
    assert not out.exists()


@pytest.mark.parametrize('field,value', [('before_sha256', 'wrong'), ('after_sha256', 'wrong'),
                                        ('file', '../escape.c'), ('package', 'foreign')])
def test_modified_file_must_be_exact_recorded_source_edit(sample, field, value):
    _, _, _, witness, proof, out = sample
    proof['explicit_edit'][field] = value
    witness.write_text(json.dumps(proof))
    with pytest.raises(ValueError):
        build(sample)
    assert not out.exists()


def test_unrelated_source_tree_must_match_original(sample):
    _, _, _, witness, proof, out = sample
    proof['preferred_source_trees']['pkg0']['tree_sha256'] = 'changed'
    witness.write_text(json.dumps(proof))
    with pytest.raises(ValueError, match='Unrelated source tree'):
        build(sample)
    assert not out.exists()


def test_modified_envelope_digest_is_checked_before_reading_arbitrary_code(sample):
    tool, _, _, _, _, out = sample
    build(sample)
    (out / 'original-kit/licensed-build-files').mkdir()
    (out / 'original-kit/licensed-build-files/evil.py').write_text('raise RuntimeError("must not execute")')
    with pytest.raises(ValueError, match='External modified manifest'):
        tool.verify_modified(out, '0' * 64)


def test_unmanifested_binary_is_rejected(sample):
    tool, _, _, _, _, out = sample
    build(sample)
    (out / 'foreign.dll').write_bytes(b'MZ')
    with pytest.raises(ValueError, match='unmanifested'):
        tool.verify_modified(out, sha((out / tool.MODIFIED_MANIFEST).read_bytes()))


def test_manifested_binary_is_still_forbidden_by_envelope_scope(sample):
    tool, _, _, _, _, out = sample
    build(sample)
    (out / 'foreign.dll').write_bytes(b'MZ')
    p = out / tool.MODIFIED_MANIFEST
    m = json.loads(p.read_text())
    m['files']['foreign.dll'] = {'sha256': sha(b'MZ'), 'size': 2}
    p.write_text(json.dumps(m))
    with pytest.raises(ValueError, match='scope forbids'):
        tool.verify_modified(out, sha(p.read_bytes()))


def test_tampering_is_rejected_even_after_internal_manifest_rehash(sample):
    tool, _, _, _, _, out = sample
    build(sample)
    p = out / 'modification-record.json'
    r = json.loads(p.read_text())
    r['legal_notice_completeness_approved'] = True
    p.write_text(json.dumps(r))
    with pytest.raises(ValueError, match='record differs'):
        tool.verify_modified(out, rehash(tool, out))


def test_all_zip_members_not_just_changed_source_are_checked(sample):
    tool, _, _, _, proof, out = sample
    build(sample)
    record = json.loads((out / 'modification-record.json').read_text())
    archive = out / 'modified-corresponding-source.zip'
    with zipfile.ZipFile(archive) as z:
        entries = [(copy.copy(e), z.read(e)) for e in z.infolist()]
        comment = z.comment
    with zipfile.ZipFile(archive, 'w') as z:
        z.comment = comment
        for info, data in entries:
            z.writestr(info, b'changed terms' if info.filename.endswith('LICENSES/L.txt') else data)
    with pytest.raises(ValueError, match='Unwitnessed modified archive content'):
        tool.verify_modified_archive(archive, out / 'original-kit', record, proof)


def test_modified_extract_preserves_symlink_execbit_and_original_mtime(sample, tmp_path):
    tool, _, _, _, _, out = sample
    build(sample)
    dest = tmp_path / 'extracted'
    tool.extract_archive(out / 'modified-corresponding-source.zip', dest)
    link = dest / 'sources/pango/v1.clean/COPYING'
    assert link.is_symlink() and link.read_bytes() == b'upstream terms'
    script = dest / 'sources/pango/v1.clean/run.sh'
    if os.name != 'nt':
        assert script.stat().st_mode & 0o111
    assert __import__('time').localtime(script.stat().st_mtime)[:6] == (2024, 2, 21, 16, 35, 54)
    assert (dest / 'VIRA-MODIFICATIONS.txt').is_file()
    with pytest.raises(FileExistsError):
        tool.extract_archive(out / 'modified-corresponding-source.zip', dest)


@pytest.mark.parametrize('args', [[], ['--verify-modified', 'x'],
    ['--modified-base-kit', 'x', '--expected-manifest-sha256', '0' * 64]])
def test_cli_missing_authentication_or_mode_inputs_fails(args):
    result = subprocess.run([sys.executable, '-I', '-S', str(ROOT / 'scripts/pdf_source_kit.py'), *args],
                            capture_output=True, text=True, check=False)
    assert result.returncode == 2


@pytest.mark.parametrize('metadata', ['external_attr', 'date_time', 'comment'])
def test_source_modes_timestamps_and_notices_cannot_be_silently_rewritten(sample, metadata):
    tool, _, _, _, proof, out = sample
    build(sample)
    record = json.loads((out / 'modification-record.json').read_text())
    path = out / 'modified-corresponding-source.zip'
    with zipfile.ZipFile(path) as archive:
        comment = archive.comment
        members = [(copy.copy(e), archive.read(e)) for e in archive.infolist()]
    with zipfile.ZipFile(path, 'w') as archive:
        archive.comment = comment
        for entry, data in members:
            if entry.filename.endswith('/run.sh'):
                if metadata == 'external_attr':
                    entry.external_attr = (stat.S_IFREG | 0o644) << 16
                elif metadata == 'date_time':
                    entry.date_time = (2026, 10, 18, 0, 0, 0)
                else:
                    entry.comment = b'rewritten original comment'
            archive.writestr(entry, data)
    with pytest.raises(ValueError, match='mode/time metadata changed'):
        tool.verify_modified_archive(path, out / 'original-kit', record, proof)


def test_inline_notice_creates_new_candidate_not_a_fabricated_prior_build(sample):
    tool, base, digest, witness, proof, out = sample
    result = tool.build_modified(base, digest, witness, sha(witness.read_bytes()), '2026-10-19', out, inline_notice=True)
    record = json.loads((out / 'modification-record.json').read_text())
    assert result['archive_variant'] == tool.INLINE_VARIANT
    assert result['inline_change_date_notice_present_in_archive_source'] is True
    assert result['prior_build_witness_applies_to_archive_sources'] is False
    assert result['new_native_build_from_this_envelope_proven'] is False
    assert record['inline_change_date_notice_present_in_compiled_source'] is False
    assert record['compiled_source_trees'] == proof['preferred_source_trees']
    assert record['archive_source_trees']['pango'] != record['compiled_source_trees']['pango']
    assert all(record['archive_source_trees'][n] == t for n, t in proof['preferred_source_trees'].items() if n != 'pango')
    with zipfile.ZipFile(out / 'modified-corresponding-source.zip') as z:
        content = z.read(record['modified_member'])
    assert content.startswith(b'/* VIRA modification notice - 2026-10-19\n')
    assert content.endswith(proof['explicit_edit']['modified_source_file'].encode())
    assert sha(content) == record['after_sha256'] != record['prior_modified_file_sha256']
    assert (out / 'native-build-witness.json').read_bytes() == witness.read_bytes()
    assert result['legal_notice_completeness_approved'] is False
    assert tool.verify_modified(out, sha((out / tool.MODIFIED_MANIFEST).read_bytes())) == result


@pytest.mark.parametrize('field,value', [
    ('prior_build_witness_applies_to_archive_sources', True),
    ('inline_change_date_notice_present_in_compiled_source', True),
    ('after_sha256', 'wrong'), ('archive_variant', 'unreviewed'),
])
def test_new_inline_notice_cannot_inherit_old_binary_attestation(sample, field, value):
    tool, base, digest, witness, _, out = sample
    tool.build_modified(base, digest, witness, sha(witness.read_bytes()), '2026-10-19', out, inline_notice=True)
    path = out / 'modification-record.json'
    record = json.loads(path.read_text())
    record[field] = value
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError):
        tool.verify_modified(out, rehash(tool, out))


def test_new_inline_notice_hash_must_cover_entire_candidate_tree(sample):
    tool, base, digest, witness, _, out = sample
    tool.build_modified(base, digest, witness, sha(witness.read_bytes()), '2026-10-19', out, inline_notice=True)
    path = out / 'modification-record.json'
    record = json.loads(path.read_text())
    record['archive_source_trees']['pango']['tree_sha256'] = record['compiled_source_trees']['pango']['tree_sha256']
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match='record differs'):
        tool.verify_modified(out, rehash(tool, out))
