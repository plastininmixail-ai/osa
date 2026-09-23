"""Конфигурация OSA.

Загрузка/сохранение TOML-конфига через pydantic v2 + tomlkit.
Конфиг хранится в $OSA_CONFIG_DIR/config.toml (по умолчанию через platformdirs).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import tomlkit
from pydantic import BaseModel, Field

from osa.paths import config_path


class LLMConfig(BaseModel):
    """Параметры LLM-провайдера."""

    provider: Literal["minimax", "openai_compat", "stub"] = "minimax"
    api_key: str | None = None
    base_url: str = "https://api.minimax.io/v1"
    model: str = "MiniMax-M3"
    timeout: float = 30.0
    max_retries: int = 3


class LoggingConfig(BaseModel):
    """Параметры логирования."""

    level: Literal["debug", "info", "warning", "error"] = "info"
    json_logs: bool = True


class OSAConfig(BaseModel):
    """Корневой конфиг OSA."""

    llm: LLMConfig = Field(default_factory=LLMConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)


def load_config(path: Path | None = None) -> OSAConfig:
    """Загрузить конфиг из TOML.

    Если файл не существует — вернуть OSAConfig() с дефолтами.
    Если TOML повреждён — выбросить tomlkit.TOMLKitError.

    После загрузки TOML применяются overrides из env (на M0 минимальный набор,
    полная поддержка pydantic-settings будет в M1a).
    """
    import os

    path = path or config_path()
    if path.exists():
        raw = path.read_text(encoding="utf-8")
        data = tomlkit.loads(raw)
        config_dict: dict = {}
        if "llm" in data:
            config_dict["llm"] = dict(data["llm"])  # type: ignore[arg-type]
        if "logging" in data:
            config_dict["logging"] = dict(data["logging"])  # type: ignore[arg-type]
        config = OSAConfig(**config_dict)
    else:
        config = OSAConfig()

    # Env overrides (минимальные, для M0)
    provider_env = os.environ.get("OSA_LLM__PROVIDER")
    if provider_env:
        config.llm.provider = provider_env  # type: ignore[assignment]
    model_env = os.environ.get("OSA_LLM__MODEL")
    if model_env:
        config.llm.model = model_env
    base_url_env = os.environ.get("OSA_LLM__BASE_URL")
    if base_url_env:
        config.llm.base_url = base_url_env

    return config


def save_default_config(path: Path) -> None:
    """Сохранить дефолтный конфиг в TOML с комментариями.

    Использует tomlkit, чтобы комментарии и форматирование сохранились
    при последующих правках через текстовый редактор.
    """
    doc = tomlkit.document()
    doc.add(tomlkit.comment("O.S.A. configuration"))
    doc.add(tomlkit.comment("Документация: docs/CONFIG.md (появится в M1a)"))
    doc.add(tomlkit.nl())

    # [llm]
    llm = tomlkit.table()
    llm.add("provider", "minimax")
    llm.add("model", "MiniMax-M3")
    llm.add("base_url", "https://api.minimax.io/v1")
    llm.add("timeout", 30.0)
    llm.add("max_retries", 3)
    llm.add(tomlkit.comment("API-ключ через env: OSA_LLM__API_KEY"))
    doc.add("llm", llm)
    doc.add(tomlkit.nl())

    # [logging]
    logging_table = tomlkit.table()
    logging_table.add("level", "info")
    logging_table.add("json_logs", True)
    doc.add("logging", logging_table)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")
