"""Тесты transports.telegram."""

from __future__ import annotations

from osa.config import OSAConfig, TelegramConfig
from osa.transports.telegram import TelegramBot


def test_telegram_bot_requires_token(tmp_osa_home) -> None:
    """TelegramBot требует bot_token."""
    config = OSAConfig()
    config.telegram = TelegramConfig(bot_token=None)

    try:
        TelegramBot(config)
        assert False, "Should have raised ValueError"
    except ValueError as e:
        assert "bot_token" in str(e)


def test_telegram_bot_creates_with_token(tmp_osa_home) -> None:
    """TelegramBot создаётся с токеном."""
    config = OSAConfig()
    config.telegram = TelegramConfig(bot_token="test-token-123")

    bot = TelegramBot(config)
    assert bot.token == "test-token-123"
    assert bot.allowed_users == set()


def test_telegram_bot_allowed_users(tmp_osa_home) -> None:
    """allowed_users загружается из конфига."""
    config = OSAConfig()
    config.telegram = TelegramConfig(
        bot_token="test", allowed_users=[123, 456]
    )

    bot = TelegramBot(config)
    assert bot.allowed_users == {123, 456}


def test_is_allowed_empty_whitelist(tmp_osa_home) -> None:
    """Пустой whitelist = разрешить всех (dev-режим)."""
    config = OSAConfig()
    config.telegram = TelegramConfig(bot_token="test", allowed_users=[])

    bot = TelegramBot(config)
    assert bot._is_allowed(123) is True
    assert bot._is_allowed(999) is True


def test_is_allowed_with_whitelist(tmp_osa_home) -> None:
    """С whitelist пропускаются только указанные user_id."""
    config = OSAConfig()
    config.telegram = TelegramConfig(
        bot_token="test", allowed_users=[123, 456]
    )

    bot = TelegramBot(config)
    assert bot._is_allowed(123) is True
    assert bot._is_allowed(456) is True
    assert bot._is_allowed(999) is False


def test_telegram_config_default(tmp_osa_home) -> None:
    """TelegramConfig по умолчанию: токен None, пустой whitelist."""
    config = TelegramConfig()
    assert config.bot_token is None
    assert config.allowed_users == []
    assert config.poll_timeout == 30.0
    assert config.auto_approve is False


def test_osa_config_includes_telegram(tmp_osa_home) -> None:
    """OSAConfig содержит telegram секцию."""
    config = OSAConfig()
    assert hasattr(config, "telegram")
    assert config.telegram.bot_token is None
