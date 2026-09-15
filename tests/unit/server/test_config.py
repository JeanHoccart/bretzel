"""Unit tests for ``bretzel.server.config``."""

from __future__ import annotations

import pytest

from bretzel.server.config import BretzelConfig, ConfigError

_OK = "x" * 32  # 32-char placeholder secret_key for tests


# ───────────────────────────────────────────────────────────────────────────
# Validation
# ───────────────────────────────────────────────────────────────────────────


class TestValidation:
    def test_secret_key_required(self) -> None:
        with pytest.raises(ConfigError, match="secret_key is required"):
            BretzelConfig(secret_key="")

    def test_secret_key_too_short(self) -> None:
        with pytest.raises(ConfigError, match="at least 16"):
            BretzelConfig(secret_key="short")

    def test_workers_must_be_positive(self) -> None:
        with pytest.raises(ConfigError, match="workers must be"):
            BretzelConfig(secret_key=_OK, workers=0)

    def test_multi_worker_needs_redis(self) -> None:
        with pytest.raises(ConfigError, match="redis_url"):
            BretzelConfig(secret_key=_OK, workers=4, redis_url=None)

    def test_session_max_age_must_be_positive(self) -> None:
        with pytest.raises(ConfigError, match="session_max_age_days"):
            BretzelConfig(secret_key=_OK, session_max_age_days=0)

    def test_mobile_breakpoint_must_be_positive(self) -> None:
        with pytest.raises(ConfigError, match="mobile_breakpoint"):
            BretzelConfig(secret_key=_OK, mobile_breakpoint=0)


# ───────────────────────────────────────────────────────────────────────────
# Frozen — config is read-only post-construction
# ───────────────────────────────────────────────────────────────────────────


class TestFrozen:
    def test_cannot_mutate(self) -> None:
        cfg = BretzelConfig(secret_key=_OK)
        with pytest.raises(Exception):
            cfg.secret_key = "rotated"  # type: ignore[misc]


# ───────────────────────────────────────────────────────────────────────────
# Defaults
# ───────────────────────────────────────────────────────────────────────────


class TestDefaults:
    def test_basic(self) -> None:
        cfg = BretzelConfig(secret_key=_OK)
        assert cfg.title == "Bretzel App"
        assert cfg.workers == 1
        assert cfg.debug is False
        assert cfg.session_max_age_days == 30
        assert cfg.redis_url is None
        assert cfg.mobile_breakpoint == 768


# ───────────────────────────────────────────────────────────────────────────
# from_kwargs — env-var fallbacks + iterable coercion
# ───────────────────────────────────────────────────────────────────────────


class TestFromKwargs:
    def test_secret_key_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BRETZEL_SECRET_KEY", _OK)
        cfg = BretzelConfig.from_kwargs()
        assert cfg.secret_key == _OK

    def test_explicit_kwarg_wins_over_env(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BRETZEL_SECRET_KEY", "x" * 16)
        cfg = BretzelConfig.from_kwargs(secret_key="y" * 16)
        assert cfg.secret_key == "y" * 16

    def test_mode_env_dev_enables_debug(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BRETZEL_SECRET_KEY", _OK)
        for dev in ("dev", "DEV", "Dev", " dev "):
            monkeypatch.setenv("BRETZEL_MODE", dev)
            cfg = BretzelConfig.from_kwargs()
            assert cfg.debug is True, dev

    def test_mode_env_non_dev_stays_prod(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BRETZEL_SECRET_KEY", _OK)
        # Anything that isn't "dev" — including unset — resolves to prod.
        for other in ("", "prod", "production", "PROD", "banana"):
            monkeypatch.setenv("BRETZEL_MODE", other)
            cfg = BretzelConfig.from_kwargs()
            assert cfg.debug is False, other

    def test_iterable_coercion(self) -> None:
        cfg = BretzelConfig.from_kwargs(
            secret_key=_OK,
            cors_origins=["https://a.com", "https://b.com"],
            trusted_hosts=["a.com", "b.com"],
        )
        # Lists land as tuples (frozen-dataclass-friendly).
        assert cfg.cors_origins == ("https://a.com", "https://b.com")
        assert cfg.trusted_hosts == ("a.com", "b.com")

    def test_missing_env_secret_key_raises(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BRETZEL_SECRET_KEY", raising=False)
        with pytest.raises(ConfigError, match="secret_key"):
            BretzelConfig.from_kwargs()
