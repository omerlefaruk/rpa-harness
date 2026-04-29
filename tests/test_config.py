"""Tests for harness config."""
import os

from harness.config import HarnessConfig, ModelConfig
from main import load_local_env


def test_config_defaults():
    config = HarnessConfig()
    assert config.name == "rpa-automation-suite"
    assert config.browser == "chromium"
    assert config.headless is False
    assert config.enable_vision is True
    assert config.enable_agent is True


def test_config_from_env():
    config = HarnessConfig.from_env()
    assert config.name
    assert config.log_level


def test_config_from_dict():
    config = HarnessConfig.from_dict({
        "name": "test-suite",
        "browser": "firefox",
        "log_level": "DEBUG",
        "models": {},
        "subagents": {},
        "variables": {},
    })
    assert config.name == "test-suite"
    assert config.browser == "firefox"


def test_model_config():
    mc = ModelConfig.from_dict({"model": "gpt-4o-mini", "temperature": 0.1})
    assert mc.model == "gpt-4o-mini"
    assert mc.temperature == 0.1


def test_config_model_routing():
    config = HarnessConfig()
    fast = config.get_model_config("fast")
    assert fast.model == "gpt-4o-mini"
    powerful = config.get_model_config("powerful")
    assert powerful.model == "gpt-4o"


def test_config_default_fallback():
    config = HarnessConfig()
    unknown = config.get_model_config("nonexistent")
    assert unknown.model == "gpt-4o-mini"


def test_load_local_env_reads_env_local_without_overriding_process_env(tmp_path, monkeypatch):
    env_file = tmp_path / ".env.local"
    env_file.write_text(
        "RPA_TELEGRAM_ENABLED=1\n"
        "RPA_TELEGRAM_CHAT_ID='local-chat'\n"
        "RPA_KEEP_EXISTING=from-file\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("RPA_TELEGRAM_ENABLED", raising=False)
    monkeypatch.delenv("RPA_TELEGRAM_CHAT_ID", raising=False)
    monkeypatch.setenv("RPA_KEEP_EXISTING", "from-process")

    load_local_env(paths=(str(env_file),))

    assert os.environ["RPA_TELEGRAM_ENABLED"] == "1"
    assert os.environ["RPA_TELEGRAM_CHAT_ID"] == "local-chat"
    assert os.environ["RPA_KEEP_EXISTING"] == "from-process"
