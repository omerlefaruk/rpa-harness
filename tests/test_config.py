"""Tests for harness config."""
from harness.config import HarnessConfig, ModelConfig, SubagentConfig


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
