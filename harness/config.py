"""
Configuration for RPA Harness.
Supports dataclass, environment variables, YAML files, and model routing.
"""

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from harness.memory.config import MemoryConfig


@dataclass
class ModelConfig:
    provider: str = "openai-compatible"
    model: str = "gpt-4o-mini"
    temperature: float = 0.1
    max_tokens: int = 4000
    api_key: Optional[str] = None
    api_base: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class SubagentConfig:
    model: str = "fast"
    timeout_seconds: int = 30
    max_parallel: int = 4
    tools: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "SubagentConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class HarnessConfig:
    name: str = "rpa-automation-suite"
    log_level: str = "INFO"
    report_dir: str = "./reports"
    screenshot_dir: str = "./screenshots"
    screenshot_on_failure: bool = True
    screenshot_on_success: bool = False
    video_record: bool = False
    slow_mo: int = 0

    # Browser / Playwright
    browser: str = "chromium"
    headless: bool = False
    viewport_width: int = 1920
    viewport_height: int = 1080
    locale: str = "en-US"
    user_agent: Optional[str] = None

    # Desktop / Windows UIAutomation
    desktop_platform: str = "windows"
    app_launch_timeout: int = 30
    element_find_timeout: int = 10

    # AI / Vision
    enable_vision: bool = True
    vision_model: str = "gpt-4o"
    vision_temperature: float = 0.2
    auto_heal_selectors: bool = True

    # Agent
    enable_agent: bool = True
    agent_model: str = "gpt-4o"
    agent_temperature: float = 0.3
    agent_max_steps: int = 50

    # Parallel execution
    max_workers: int = 4

    # LLM Provider (OpenAI-compatible)
    openai_api_key: Optional[str] = None
    openai_api_base: Optional[str] = None

    # Model routing
    models: Dict[str, ModelConfig] = field(default_factory=dict)
    subagents: Dict[str, SubagentConfig] = field(default_factory=dict)

    # Memory
    memory: MemoryConfig = field(default_factory=MemoryConfig)

    # Custom variables for workflows
    variables: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls) -> "HarnessConfig":
        return cls(
            name=os.getenv("RPA_NAME", "rpa-automation-suite"),
            log_level=os.getenv("RPA_LOG_LEVEL", "INFO"),
            report_dir=os.getenv("RPA_REPORT_DIR", "./reports"),
            browser=os.getenv("RPA_BROWSER", "chromium"),
            headless=os.getenv("RPA_HEADLESS", "false").lower() == "true",
            viewport_width=int(os.getenv("RPA_VIEWPORT_W", "1920")),
            viewport_height=int(os.getenv("RPA_VIEWPORT_H", "1080")),
            enable_vision=os.getenv("RPA_ENABLE_VISION", "true").lower() == "true",
            enable_agent=os.getenv("RPA_ENABLE_AGENT", "true").lower() == "true",
            auto_heal_selectors=os.getenv("RPA_AUTO_HEAL", "true").lower() == "true",
            max_workers=int(os.getenv("RPA_MAX_WORKERS", "4")),
            openai_api_key=os.getenv("OPENAI_API_KEY"),
            openai_api_base=os.getenv("OPENAI_API_BASE"),
            memory=MemoryConfig.from_env(),
        )

    @classmethod
    def from_dict(cls, data: dict) -> "HarnessConfig":
        known_fields = set(cls.__dataclass_fields__.keys())
        filtered = {}

        for k, v in data.items():
            if k == "models" and isinstance(v, dict):
                filtered[k] = {
                    name: ModelConfig.from_dict(cfg) for name, cfg in v.items()
                }
            elif k == "subagents" and isinstance(v, dict):
                filtered[k] = {
                    name: SubagentConfig.from_dict(cfg) for name, cfg in v.items()
                }
            elif k == "memory" and isinstance(v, dict):
                filtered[k] = MemoryConfig(**v)
            elif k in known_fields:
                filtered[k] = v

        return cls(**filtered)

    @classmethod
    def from_yaml(cls, path: str) -> "HarnessConfig":
        import yaml
        with open(path) as f:
            data = yaml.safe_load(f)
        config = cls.from_dict(data)

        config.openai_api_key = os.getenv("OPENAI_API_KEY", config.openai_api_key)
        config.openai_api_base = os.getenv("OPENAI_API_BASE", config.openai_api_base)

        return config

    def ensure_dirs(self):
        for d in [self.report_dir, self.screenshot_dir]:
            Path(d).mkdir(parents=True, exist_ok=True)
        if self.memory.enabled:
            Path(self.memory.db_path).parent.mkdir(parents=True, exist_ok=True)

    def get_model_config(self, name: str) -> ModelConfig:
        if name in self.models:
            return self.models[name]
        defaults = {
            "fast": ModelConfig(model="gpt-4o-mini", temperature=0.1, max_tokens=4000),
            "powerful": ModelConfig(model="gpt-4o", temperature=0.2, max_tokens=8000),
            "vision": ModelConfig(model="gpt-4o", temperature=0.1, max_tokens=4000),
        }
        return defaults.get(name, defaults["fast"])

    def get_subagent_config(self, name: str) -> SubagentConfig:
        if name in self.subagents:
            return self.subagents[name]
        return SubagentConfig()

    def get_openai_client_kwargs(self) -> dict:
        kwargs: dict = {}
        if self.openai_api_key:
            kwargs["api_key"] = self.openai_api_key
        if self.openai_api_base:
            kwargs["base_url"] = self.openai_api_base
        return kwargs
