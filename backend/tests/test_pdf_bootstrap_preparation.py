"""ALL payloads/native bytes here are FAKE; no Windows/native/installed proof."""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import private_pdf_bootstrap as boot

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def put(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding='utf-8')


def stamp(root, state):
    files = [{'path': p.relative_to(root).as_posix(), 'size': p.stat().st_size, 'sha256': digest(p)}
             for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'install_manifest.json']
    put(root/'install_manifest.json', {'files': files})
    return boot.PrivateBootstrapPlan(root, state, digest(root/'install_manifest.json'),
                                     digest(root/'native/pdf/runtime-inventory.json'))


@pytest.fixture()
def payload(tmp_path):
    root, state = tmp_path/'برنامه & مسیر خصوصی', tmp_path/'کاربر آزمایشی با فاصله'/'وضعیت تازه'
    for relative in boot.REQUIRED:
        file = root/relative
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'FAKE, NOT DLL, FONT OR WINDOWS PROOF')
    (root/'app/private_pdf_bootstrap.py').write_bytes(Path(boot.__file__).read_bytes())
    put(root/'version.json', {'version': '0.0.0-private-unicode-proof'})
    put(root/'private-utf8-process-manifest.json', {
        'private_only': True, 'python_executable_is_unmodified_upstream_binary': False,
        'release_or_redistribution_approval': False, 'executable_sha256_before': '0'*64,
        'executable_sha256_after': digest(root/'python/python.exe'),
    })
    dlls = {}
    for name in ['libffi-8.dll', *[f'fake-{i}.dll' for i in range(26)]]:
        file = root/'native/pdf/bin'/name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(b'FAKE DLL; NO NATIVE COMPILATION')
        dlls[name] = {'sha256': digest(file)}
    put(root/'native/pdf/runtime-inventory.json', {
        'upstream': {'sha256': boot.SDK_SHA256}, 'dlls': dlls,
        'distribution_status': boot.BLOCKED, 'preload_dlls': ['libffi-8.dll'],
    })
    return stamp(root, state)


def tree(root):
    return {p.relative_to(root).as_posix(): digest(p) for p in root.rglob('*') if p.is_file()}


def test_read_only_data_snapshot_has_no_side_effects_or_native_import(payload):
    before = tree(payload.payload_root), dict(os.environ), sys.path[:], tempfile.tempdir, set(sys.modules)
    verified = boot.verify_private_plan(payload)
    assert verified.scope == 'PRIVATE_SDK_PREFLIGHT_ONLY_NO_NATIVE_ACTIVATION'
    assert len(verified.dlls) == 27 and isinstance(verified.dlls, tuple)
    assert verified.preload == payload.payload_root/'native/pdf/bin/libffi-8.dll'
    assert verified.cache_root == payload.state_root/'pdf-cache'
    assert not payload.state_root.exists()
    assert (tree(payload.payload_root), dict(os.environ), sys.path[:], tempfile.tempdir) == before[:4]
    added = set(sys.modules) - before[4]
    assert not any(n == p or n.startswith(p + '.') for n in added
                   for p in ('app', 'cffi', 'ctypes', 'weasyprint', 'uvicorn', 'fastapi', 'pydantic'))
    with pytest.raises(FrozenInstanceError):
        verified.scope = 'approved'
    with pytest.raises(FrozenInstanceError):
        payload.manifest_sha256 = '0'*64


@pytest.mark.parametrize('value', [None, {}, SimpleNamespace(), lambda: None])
def test_no_executable_or_untyped_policy(value):
    with pytest.raises(TypeError):
        boot.verify_private_plan(value)
    with pytest.raises(TypeError):
        boot.prepare_private_plan(value)


@pytest.mark.parametrize('fault', ['relative-root', 'root-root', 'traversal', 'nested-state', 'nested-payload',
                                 'relative-state', 'invalid-hash', 'uppercase-hash'])
def test_plan_rejects_ambiguous_paths_and_digests(payload, fault):
    changes = {
        'relative-root': {'payload_root': Path('relative')},
        'root-root': {'payload_root': Path(payload.payload_root.anchor)},
        'traversal': {'payload_root': payload.payload_root/'..'/'other'},
        'nested-state': {'state_root': payload.payload_root/'state'},
        'nested-payload': {'state_root': payload.payload_root.parent},
        'relative-state': {'state_root': Path('relative')},
        'invalid-hash': {'inventory_sha256': 'x'*64},
        'uppercase-hash': {'manifest_sha256': 'A'*64},
    }
    with pytest.raises(ValueError):
        replace(payload, **changes[fault])


@pytest.mark.parametrize('field', ['manifest_sha256', 'inventory_sha256'])
def test_external_digest_is_not_recomputed_on_mismatch(payload, field):
    with pytest.raises(ValueError, match='Independent digest mismatch'):
        boot.verify_private_plan(replace(payload, **{field: 'f'*64}))


@pytest.mark.parametrize('file', ['python/python.exe', 'app/main.py', 'app/services/pdf_rendering.py',
                                 'native/pdf/bin/libffi-8.dll', 'app/assets/fonts/Vazirmatn-Regular.ttf'])
def test_payload_drift_requires_new_independent_baseline(payload, file):
    (payload.payload_root/file).write_bytes(b'changed')
    with pytest.raises(ValueError, match='Baseline file changed'):
        boot.verify_private_plan(payload)


@pytest.mark.parametrize('name', ['site-packages/shadow.py', 'app/unlisted.py', 'native/pdf/bin/foreign.dll'])
def test_unmanifested_files_are_rejected(payload, name):
    (payload.payload_root/name).write_bytes(b'not in baseline')
    with pytest.raises(ValueError, match='unmanifested'):
        boot.verify_private_plan(payload)


def test_manifested_but_uninventoried_native_is_not_accepted(payload):
    (payload.payload_root/'native/pdf/bin/foreign.DLL').write_bytes(b'FAKE')
    plan = stamp(payload.payload_root, payload.state_root)
    with pytest.raises(ValueError, match='Uninventoried native'):
        boot.verify_private_plan(plan)


@pytest.mark.parametrize('name', ['../outside', 'a/../outside', '/outside', 'C:relative', 'C:/root',
                                 '//host/share', 'a\\b', 'file:stream', './file', 'a//file', '',
                                 'CON', 'aux.txt', 'COM1.dll', 'a./file', 'file ', 'a?b', 'a\x00b'])
def test_cross_platform_aliases_and_escapes_fail_before_access(payload, name):
    with pytest.raises(ValueError, match='Unsafe or aliased'):
        boot._member(payload.payload_root, name)


@pytest.mark.parametrize('fault', ['alias', 'recursive', 'size-bool', 'missing', 'entry-type', 'files-type'])
def test_manifest_schema_and_required_members(payload, fault):
    path = payload.payload_root/'install_manifest.json'
    manifest = json.loads(path.read_text())
    if fault == 'alias':
        manifest['files'].append({**manifest['files'][0], 'path': manifest['files'][0]['path'].upper()})
    elif fault == 'recursive':
        manifest['files'].append({'path': 'install_manifest.json', 'size': 0, 'sha256': '0'*64})
    elif fault == 'size-bool':
        manifest['files'][0]['size'] = True
    elif fault == 'missing':
        manifest['files'] = [e for e in manifest['files'] if e['path'] != 'app/main.py']
    elif fault == 'entry-type':
        manifest['files'].append('not-an-object')
    else:
        manifest['files'] = {}
    put(path, manifest)
    with pytest.raises(ValueError):
        boot.verify_private_plan(replace(payload, manifest_sha256=digest(path)))


@pytest.mark.parametrize('fault', ['source21', 'sdk', 'status', 'count', 'preload', 'dll-hash', 'dll-alias',
                                 'version', 'pe-approval', 'pe-unchanged', 'different-code', 'upstream-type'])
def test_no_source_distribution_or_native_policy_fallback(payload, fault):
    root = payload.payload_root
    file = root/'native/pdf/runtime-inventory.json'
    inventory = json.loads(file.read_text())
    if fault == 'source21':
        inventory['origin'] = 'LOCAL_PINNED_VCPKG_SOURCE_BUILD'
    elif fault == 'sdk':
        inventory['upstream']['sha256'] = '0'*64
    elif fault == 'upstream-type':
        inventory['upstream'] = None
    elif fault == 'status':
        inventory['distribution_status'] = 'APPROVED'
    elif fault == 'count':
        inventory['dlls'].pop('fake-0.dll')
    elif fault == 'preload':
        inventory['preload_dlls'] = ['ffi-8.dll']
    elif fault == 'dll-hash':
        inventory['dlls']['libffi-8.dll']['sha256'] = '0'*64
    elif fault == 'dll-alias':
        inventory['dlls']['FAKE-0.DLL'] = inventory['dlls'].pop('fake-1.dll')
    elif fault == 'version':
        put(root/'version.json', {'version': '1.0.10'})
    elif fault.startswith('pe-'):
        pefile = root/'private-utf8-process-manifest.json'
        pe = json.loads(pefile.read_text())
        if fault == 'pe-approval':
            pe['release_or_redistribution_approval'] = True
        else:
            pe['executable_sha256_before'] = pe['executable_sha256_after']
        put(pefile, pe)
    else:
        (root/'app/private_pdf_bootstrap.py').write_bytes(b'other code')
    put(file, inventory)
    with pytest.raises(ValueError):
        boot.verify_private_plan(stamp(root, payload.state_root))


@pytest.mark.parametrize('raw', ['{"files":[],"files":[]}', '{"files":NaN}', '[]'])
def test_noncanonical_json_is_rejected(payload, raw):
    path = payload.payload_root/'install_manifest.json'
    path.write_text(raw)
    with pytest.raises(ValueError):
        boot.verify_private_plan(replace(payload, manifest_sha256=digest(path)))


@pytest.mark.parametrize('kind', ['root', 'member', 'state', 'ancestor'])
def test_links_never_redirect_payload_or_state(payload, tmp_path, kind):
    root, state = payload.payload_root, payload.state_root
    if kind == 'root':
        link = tmp_path/'root link'
        link.symlink_to(root, target_is_directory=True)
        payload = replace(payload, payload_root=link)
    elif kind == 'member':
        file = root/'app/main.py'
        target = tmp_path/'outside.py'
        target.write_bytes(file.read_bytes())
        file.unlink()
        file.symlink_to(target)
    elif kind == 'state':
        target = tmp_path/'state target'
        target.mkdir()
        state.parent.mkdir()
        state.symlink_to(target, target_is_directory=True)
    else:
        target = tmp_path/'ancestor target'
        target.mkdir()
        state.parent.symlink_to(target, target_is_directory=True)
    with pytest.raises(ValueError, match='Symlink/reparse'):
        boot.verify_private_plan(payload)


def test_existing_state_is_not_reused_or_removed(payload):
    payload.state_root.mkdir(parents=True)
    sentinel = payload.state_root/'not-yours'
    sentinel.write_bytes(b'preserve')
    with pytest.raises(ValueError, match='fresh empty'):
        boot.verify_private_plan(payload)
    assert sentinel.read_bytes() == b'preserve'


def test_snapshot_is_not_authority_after_mutation(payload):
    verified = boot.verify_private_plan(payload)
    (payload.payload_root/'app/main.py').write_bytes(b'changed after verification')
    assert verified.scope.endswith('NO_NATIVE_ACTIVATION')
    with pytest.raises(ValueError):
        boot.verify_private_plan(verified.plan)


def test_import_is_stdlib_only_in_fresh_isolated_process():
    code = f'''import runpy,sys,os,tempfile
before=(dict(os.environ),sys.path[:],tempfile.tempdir)
runpy.run_path({str(Path(boot.__file__))!r},run_name='preflight_import_test')
assert before==(dict(os.environ),sys.path[:],tempfile.tempdir)
assert not any(n==p or n.startswith(p+'.') for n in sys.modules for p in ('app','cffi','ctypes','weasyprint','uvicorn','fastapi','pydantic'))
'''
    subprocess.run([sys.executable, '-I', '-S', '-B', '-X', 'utf8', '-c', code], check=True)


@pytest.fixture()
def private_process(payload, monkeypatch):
    flags = SimpleNamespace(**dict.fromkeys(('isolated', 'no_site', 'dont_write_bytecode', 'utf8_mode'), 1))
    runtime = SimpleNamespace(platform='win32', flags=flags, version_info=(3, 11, 0),
                             executable=str(payload.payload_root/'python/python.exe'),
                             base_prefix=str(payload.payload_root/'python'),
                             modules={'app': SimpleNamespace(__file__=str(payload.payload_root/'app/__init__.py'),
                                                            __path__=[str(payload.payload_root/'app')]),
                                      boot.__name__: boot})
    monkeypatch.setattr(boot, 'sys', runtime)
    monkeypatch.setattr(boot, '__file__', str(payload.payload_root/'app/private_pdf_bootstrap.py'))
    monkeypatch.setenv('GITHUB_ACTIONS', 'true')
    monkeypatch.setenv('RUNNER_TEMP', str(payload.payload_root.parent))
    monkeypatch.setenv('LOCALAPPDATA', str(payload.state_root.parent))
    cwd = payload.state_root.parent/'محل اجرای جدا'
    cwd.mkdir(parents=True)
    monkeypatch.chdir(cwd)
    return runtime


@pytest.mark.parametrize('fault', ['platform', 'ci', 'isolated', 'no_site', 'dont_write_bytecode', 'utf8_mode',
                                 'version', 'early-ctypes', 'early-weasyprint', 'early-app', 'early-cffi',
                                 'early-sitecustomize'])
def test_process_guards_fail_before_payload_reads(payload, private_process, monkeypatch, fault):
    runtime = private_process
    if fault == 'platform':
        runtime.platform = 'linux'
    elif fault == 'ci':
        monkeypatch.setenv('GITHUB_ACTIONS', 'false')
    elif fault == 'version':
        runtime.version_info = (3, 12, 0)
    elif fault.startswith('early-'):
        name = {'early-ctypes': 'ctypes', 'early-weasyprint': 'weasyprint.text', 'early-app': 'app.main',
                'early-cffi': '_cffi_backend', 'early-sitecustomize': 'sitecustomize'}[fault]
        runtime.modules[name] = object()
    else:
        setattr(runtime.flags, fault, 0)
    def unread(*_):
        raise AssertionError('Payload must not be read after failed process guard')
    monkeypatch.setattr(boot, 'verify_private_plan', unread)
    with pytest.raises(RuntimeError):
        boot.prepare_private_plan(payload)


def test_simulated_private_process_enters_read_only_plan_not_native(payload, private_process):
    # Simulated flags/paths only, explicitly NOT a real Windows result.
    result = boot.prepare_private_plan(payload)
    assert result.plan == payload and result.scope.endswith('NO_NATIVE_ACTIVATION')
    assert not payload.state_root.exists()


@pytest.mark.parametrize('fault', ['foreign-executable', 'foreign-prefix', 'foreign-code', 'foreign-profile',
                                 'foreign-cwd', 'runner-is-payload', 'symlink-profile', 'foreign-app-package'])
def test_process_path_guards_precede_payload_reads(payload, private_process, monkeypatch, fault, tmp_path):
    if fault == 'foreign-executable':
        private_process.executable = str(tmp_path/'python.exe')
    elif fault == 'foreign-prefix':
        private_process.base_prefix = str(tmp_path/'python')
    elif fault == 'foreign-code':
        monkeypatch.setattr(boot, '__file__', str(tmp_path/'private_pdf_bootstrap.py'))
    elif fault == 'foreign-app-package':
        private_process.modules['app'].__path__ = [str(tmp_path/'foreign-app')]
    elif fault == 'foreign-profile':
        monkeypatch.setenv('LOCALAPPDATA', str(tmp_path.parent/'foreign-profile'))
    elif fault == 'foreign-cwd':
        monkeypatch.chdir(tmp_path)
    elif fault == 'runner-is-payload':
        monkeypatch.setenv('RUNNER_TEMP', str(payload.payload_root))
    else:
        link = tmp_path/'profile link'
        link.symlink_to(payload.state_root.parent, target_is_directory=True)
        monkeypatch.setenv('LOCALAPPDATA', str(link))
    def unread(*_):
        raise AssertionError('Payload read after unsafe path guard')
    monkeypatch.setattr(boot, 'verify_private_plan', unread)
    with pytest.raises(ValueError):
        boot.prepare_private_plan(payload)


def test_ordinary_default_factory_has_no_preflight_opt_in():
    import inspect

    from app.main import create_app
    source = inspect.getsource(create_app)
    assert 'private_pdf_bootstrap' not in source
    assert inspect.signature(create_app).parameters['private_pdf_policy'].default is None


def test_whole_synthetic_verifier_is_stdlib_only_in_fresh_process(payload):
    code = f'''import runpy,sys,os,tempfile
from pathlib import Path
ns=runpy.run_path({str(Path(boot.__file__))!r},run_name='preflight_verifier_test')
p=ns['PrivateBootstrapPlan'](Path({str(payload.payload_root)!r}),Path({str(payload.state_root)!r}),
    {payload.manifest_sha256!r},{payload.inventory_sha256!r})
before=(dict(os.environ),sys.path[:],tempfile.tempdir)
v=ns['verify_private_plan'](p)
assert v.scope=='PRIVATE_SDK_PREFLIGHT_ONLY_NO_NATIVE_ACTIVATION'
assert len(v.dlls)==27 and not p.state_root.exists()
assert before==(dict(os.environ),sys.path[:],tempfile.tempdir)
assert not any(n==p or n.startswith(p+'.') for n in sys.modules
               for p in ('app','cffi','ctypes','weasyprint','uvicorn','fastapi','pydantic'))
'''
    subprocess.run([sys.executable, '-I', '-S', '-B', '-X', 'utf8', '-c', code], check=True)


def test_reparse_bit_uses_lstat_not_followed_stat_or_exists():
    # Synthetic attribute check, NOT actual NTFS junction evidence.
    def forbidden():
        raise AssertionError('Following stat/exists could hide a junction')
    path = SimpleNamespace(parents=(), is_symlink=lambda: False,
                           lstat=lambda: SimpleNamespace(st_file_attributes=0x400),
                           stat=forbidden, exists=forbidden)
    with pytest.raises(ValueError, match='Symlink/reparse'):
        boot._no_links(path)
