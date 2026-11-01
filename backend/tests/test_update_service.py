"""Phase 8 §3/§8 — update channel service: ETag caching, rate-limit handling,
APP_UPDATE_URL override, schema refusal, delta selection, staging verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.config import Settings
from app.services import update as update_mod
from app.services.update import UpdateChannelError, check_for_update, fetch_channel, manager
from app.services.update_engine import VerificationError, sha256_bytes


def _latest_bytes(**over: object) -> bytes:
    payload = {
        "schema_version": 1,
        "version": "2.0.0",
        "pub_date": "2026-10-14T12:00:00Z",
        "min_app_version": "1.0.0",
        "notes_fa": "نسخهٔ ۲",
        "notes_en": "v2",
        "full_installer": {
            "url": "https://github.com/x/y/releases/download/v2.0.0/NOA-Setup-2.0.0.exe",
            "sha256": "ab" * 32,
            "size": 50_000_000,
        },
        "deltas": [
            {
                "from_version": "1.5.0",
                "url": "https://github.com/x/y/releases/download/v2.0.0/NOA-2.0.0-delta-from-1.5.0.zip",
                "sha256": "cd" * 32,
                "size": 250_000,
            }
        ],
        "files_manifest_sha256": "ef" * 32,
    }
    payload.update(over)
    return json.dumps(payload).encode("utf-8")


class _Resp:
    def __init__(
        self,
        status: int,
        content: bytes,
        etag: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        self.status_code = status
        self.content = content
        self.headers = dict(headers or {})
        if etag:
            self.headers["ETag"] = etag


def _settings(tmp_path: Path, **over: object) -> Settings:
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    return Settings(
        environment="development",
        data_dir=data,
        update_github_repo="x/y",
        app_update_url=str(over.pop("app_update_url", "")),
        update_public_key=str(over.pop("update_public_key", "")),
        **over,
    )


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    update_mod._etag_cache.clear()
    yield
    update_mod._etag_cache.clear()


class TestChannel:
    def test_app_update_url_override(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = _latest_bytes()

        def fake_get(url: str, **kw: object) -> _Resp:
            assert url == "https://mirror.example/latest.json"
            return _Resp(200, raw, '"etag-1"')

        monkeypatch.setattr("httpx.get", fake_get)
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        channel = fetch_channel(s)
        assert channel.manifest.version == "2.0.0"

    def test_etag_304_uses_cache(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        raw = _latest_bytes()
        calls: list[str | None] = []

        def fake_get(url: str, **kw: object) -> _Resp:
            headers = kw.get("headers") or {}
            calls.append(headers.get("If-None-Match"))
            if headers.get("If-None-Match") == '"e1"':
                return _Resp(304, b"")
            return _Resp(200, raw, '"e1"')

        monkeypatch.setattr("httpx.get", fake_get)
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        fetch_channel(s)
        fetch_channel(s)  # second call must be conditional
        assert calls == [None, '"e1"']

    @pytest.mark.parametrize(
        ("status", "headers", "body"),
        [
            (429, {}, b""),
            (403, {"X-RateLimit-Remaining": "0"}, b""),
            (403, {"Retry-After": "900"}, b""),
            (403, {}, b'{"message": "API rate limit exceeded for 1.2.3.4."}'),
        ],
    )
    def test_rate_limit_persian_retry_later(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        status: int,
        headers: dict[str, str],
        body: bytes,
    ) -> None:
        monkeypatch.setattr(
            "httpx.get", lambda url, **kw: _Resp(status, body, headers=headers)
        )
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.5.0", s)
        assert result.checked is False
        assert result.reason_fa is not None and "کمی بعد" in result.reason_fa

    def test_rate_limit_message_states_the_real_wait(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "httpx.get",
            lambda url, **kw: _Resp(429, b"", headers={"Retry-After": "600"}),
        )
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.5.0", s)
        assert result.reason_fa is not None
        assert "حدود ۱۰ دقیقهٔ دیگر" in result.reason_fa

    def test_a_bare_403_is_not_reported_as_a_quota_problem(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """«تعداد درخواست‌ها بیش از حد مجاز» sent the owner hunting a quota
        that was not the cause; a region block or a denied link is not a quota."""
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(403, b"Forbidden"))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.5.0", s)
        assert result.checked is False
        assert result.reason_fa is not None
        assert "بیش از حد مجاز" not in result.reason_fa
        assert "ممکن نشد" in result.reason_fa

    def test_unknown_schema_refused(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "httpx.get", lambda url, **kw: _Resp(200, _latest_bytes(schema_version=99))
        )
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.5.0", s)
        assert result.checked is False
        assert result.reason_fa is not None and "دستی" in result.reason_fa

    def test_ed25519_signature_enforced_when_key_baked(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

        key = Ed25519PrivateKey.generate()
        pub_pem = key.public_key().public_bytes(
            serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        pem_path = tmp_path / "update.pub"
        pem_path.write_bytes(pub_pem)
        raw = _latest_bytes()
        bad_sig = b"\x00" * 64

        def fake_get(url: str, **kw: object) -> _Resp:
            if url.endswith(".sig"):
                return _Resp(200, bad_sig)
            return _Resp(200, raw)

        monkeypatch.setattr("httpx.get", fake_get)
        # The mirror must provide a valid detached signature when a key is configured.
        s = _settings(
            tmp_path,
            app_update_url="https://mirror.example/latest.json",
            update_public_key=str(pem_path),
        )
        # Once a trusted key is configured, a missing/invalid signature is NOT optional.
        with pytest.raises(UpdateChannelError):
            fetch_channel(s)


class TestNoQuotaChannel:
    """The real GitHub release asset, never the anonymous REST quota."""

    def test_the_check_never_touches_the_rate_limited_api(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        def fake_get(url: str, **kw: object) -> _Resp:
            seen.append(url)
            return _Resp(200, _latest_bytes())

        monkeypatch.setattr("httpx.get", fake_get)
        channel = fetch_channel(_settings(tmp_path))
        assert channel.manifest.version == "2.0.0"
        assert seen == [
            "https://github.com/x/y/releases/latest/download/latest.json"
        ]
        assert all("api.github.com" not in url for url in seen)

    def test_no_signature_request_without_a_trusted_key(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[str] = []

        def fake_get(url: str, **kw: object) -> _Resp:
            seen.append(url)
            return _Resp(200, _latest_bytes())

        monkeypatch.setattr("httpx.get", fake_get)
        fetch_channel(_settings(tmp_path))
        # 1.0.x publishes no latest.json.sig; asking for it wastes a request.
        assert not any(url.endswith(".sig") for url in seen)

    def test_api_is_asked_only_when_the_release_has_no_latest_json(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        raw = _latest_bytes()
        seen: list[str] = []

        def fake_get(url: str, **kw: object) -> _Resp:
            seen.append(url)
            if "api.github.com" in url:
                return _Resp(
                    200,
                    json.dumps(
                        {
                            "assets": [
                                {
                                    "name": "latest.json",
                                    "browser_download_url": "https://cdn.example/l.json",
                                }
                            ]
                        }
                    ).encode(),
                )
            if url == "https://cdn.example/l.json":
                return _Resp(200, raw)
            return _Resp(404, b"Not Found")  # an older release without the asset

        monkeypatch.setattr("httpx.get", fake_get)
        channel = fetch_channel(_settings(tmp_path))
        assert channel.manifest.version == "2.0.0"
        assert seen[0].endswith("/releases/latest/download/latest.json")
        assert "api.github.com" in seen[1]

    def test_an_unreachable_release_does_not_spend_api_quota(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A network failure must not become a second, quota-burning attempt."""
        import httpx

        seen: list[str] = []

        def fake_get(url: str, **kw: object) -> _Resp:
            seen.append(url)
            raise httpx.ConnectError("no route to host")

        monkeypatch.setattr("httpx.get", fake_get)
        with pytest.raises(UpdateChannelError):
            fetch_channel(_settings(tmp_path))
        assert len(seen) == 1


class TestCheck:
    def test_delta_preferred_when_base_matches(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(200, _latest_bytes()))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.5.0", s)
        assert result.update_available is True
        assert result.choice is not None
        assert result.choice.kind == "delta"
        assert result.choice.total_bytes == 250_000  # only the changed parts

    def test_full_fallback_for_old_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(200, _latest_bytes()))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        # above min_app_version but below every delta base → full installer
        result = check_for_update("1.0.0", s)
        assert result.choice is not None
        assert result.choice.kind == "full"
        assert result.choice.total_bytes == 50_000_000

    def test_manual_required_below_min_app_version(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "httpx.get", lambda url, **kw: _Resp(200, _latest_bytes(min_app_version="1.9.0"))
        )
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.0.0", s)
        assert result.manual_required is True

    @pytest.mark.parametrize("current", ["0.0.0-unknown", "unknown", "", "1.0"])
    def test_unstamped_current_never_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, current: str
    ) -> None:
        """Regression: v1.0.4 crashed with SemVerError on «0.0.0-unknown»."""
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(200, _latest_bytes()))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update(current, s)  # must not raise
        assert result.checked is True
        assert result.update_available is True
        assert result.manual_required is True
        assert result.reason_fa is not None and "فایل نصب کامل" in result.reason_fa
        assert result.choice is not None and result.choice.kind == "full"
        assert result.choice.total_bytes == 50_000_000

    def test_unstamped_current_reports_no_update_when_nothing_newer(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An unstamped install still gets a sane answer for an old manifest."""
        monkeypatch.setattr(
            "httpx.get", lambda url, **kw: _Resp(200, _latest_bytes(version="0.0.0"))
        )
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("0.0.0-unknown", s)
        assert result.checked is True
        assert result.manual_required is True

    def test_unparseable_manifest_version_refused(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "httpx.get", lambda url, **kw: _Resp(200, _latest_bytes(version="nightly"))
        )
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("1.5.0", s)
        assert result.checked is False
        assert result.reason_fa is not None and "دستی" in result.reason_fa

    def test_no_update_when_current_is_latest(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(200, _latest_bytes()))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        result = check_for_update("2.0.0", s)
        assert result.update_available is False
        assert result.checked is True


class TestUpdaterDiscovery:
    """The helper must be found in the installed layout, not just in staging."""

    def _install_tree(self, tmp_path: Path) -> Path:
        root = tmp_path / "app"
        (root / "scripts").mkdir(parents=True)
        (root / "version.json").write_text('{"version": "1.0.5", "commit": "abc1234"}')
        (root / "python").mkdir()
        return root

    def test_finds_helper_in_install_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.update import _updater_command

        root = self._install_tree(tmp_path)
        (root / "noa-updater.exe").write_bytes(b"MZ")
        stage = tmp_path / "stage"
        stage.mkdir()
        monkeypatch.setenv("NOA_APP_DIR", str(root))
        s = _settings(tmp_path)
        argv, log = _updater_command(s, str(stage))
        assert argv[0] == str(root / "noa-updater.exe")
        # single-dash PowerShell parameters (asserted verbatim — the exe is a
        # compiled PowerShell script) and the install dir passed explicitly, so
        # no registry record is required for portable/unzipped installs.
        assert argv[1:5] == ["-stage", str(stage), "-log", str(stage / "update.log")]
        assert "-InstallDir" in argv
        assert argv[argv.index("-InstallDir") + 1] == str(root)
        assert log == stage / "update.log"

    def test_falls_back_to_shipped_powershell_helper(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.update import _updater_command

        root = self._install_tree(tmp_path)
        (root / "scripts" / "noa_updater.ps1").write_text("# updater")
        stage = tmp_path / "stage"
        stage.mkdir()
        monkeypatch.setenv("NOA_APP_DIR", str(root))
        argv, _ = _updater_command(_settings(tmp_path), str(stage))
        assert argv[0] == "powershell.exe"
        assert "-InstallDir" in argv and argv[argv.index("-InstallDir") + 1] == str(root)

    def test_missing_helper_raises_persian_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.errors import DomainError
        from app.services.update import _updater_command

        stage = tmp_path / "stage"
        stage.mkdir()
        monkeypatch.delenv("NOA_APP_DIR", raising=False)
        monkeypatch.setenv("NOA_VERSION", "1.0.5")
        with pytest.raises(DomainError) as excinfo:
            _updater_command(_settings(tmp_path), str(stage))
        assert "فایل نصب کامل" in str(excinfo.value)


class TestDownload:
    def test_staging_verifies_sha256_before_write(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        payload = b"delta-package-bytes"
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(200, _latest_bytes()))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        check = check_for_update("1.5.0", s)
        assert check.choice is not None
        check.choice.packages[0]["size"] = len(payload)
        check.choice.total_bytes = len(payload)

        class _StreamResp:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def iter_bytes(self, n: int):
                yield payload

            def __enter__(self):
                return self

            def __exit__(self, *a: object):
                return False

        monkeypatch.setattr("httpx.stream", lambda *a, **kw: _StreamResp())
        # corrupt the expected hash to force failure
        check.choice.packages[0]["sha256"] = "ff" * 32
        with pytest.raises(VerificationError):
            manager.start_download(check, s)
        status = manager.status()
        assert status["state"] == "failed"
        assert status["error_fa"] is not None
        # nothing unverified was staged as ready
        assert status["verified"] is False

    def test_successful_download_stages_verified_package(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from tests.test_update_download_flow import delta_bytes

        payload = delta_bytes()
        monkeypatch.setattr("httpx.get", lambda url, **kw: _Resp(200, _latest_bytes()))
        s = _settings(tmp_path, app_update_url="https://mirror.example/latest.json")
        check = check_for_update("1.5.0", s)
        assert check.choice is not None
        check.choice.packages[0]["sha256"] = sha256_bytes(payload)
        check.choice.packages[0]["size"] = len(payload)
        check.choice.total_bytes = len(payload)

        class _StreamResp:
            status_code = 200

            def raise_for_status(self) -> None:
                return None

            def iter_bytes(self, n: int):
                yield payload

            def __enter__(self):
                return self

            def __exit__(self, *a: object):
                return False

        monkeypatch.setattr("httpx.stream", lambda *a, **kw: _StreamResp())
        status = manager.start_download(check, s)
        assert status["state"] == "staged"
        assert status["verified"] is True
        staged = Path(status["staged_path"])
        assert (staged.parent / "package.zip").read_bytes() == payload
        assert (staged / "update.json").is_file()
        assert (staged / "noa-updater.exe").is_file()
        assert Path(status["log_path"]).is_file()
