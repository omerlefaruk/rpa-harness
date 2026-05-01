"""
Subagent base class — LLM client + tool registry for dispatachable agents.
"""

import json
from typing import Any, Callable, Dict, List, Optional

from harness.config import HarnessConfig, ModelConfig
from harness.logger import HarnessLogger


class BaseSubagent:
    subagent_name: str = "base"
    default_model: str = "fast"

    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config or HarnessConfig.from_env()
        self.logger = HarnessLogger(f"subagent.{self.subagent_name}")
        self._client = None
        self._model_config: Optional[ModelConfig] = None

    def _get_client(self):
        if self._client is None:
            from openai import OpenAI
            kwargs = self.config.get_openai_client_kwargs()
            self._client = OpenAI(**kwargs)
        return self._client

    def _model(self) -> str:
        if not self._model_config:
            self._model_config = self.config.get_model_config(self.default_model)
        return self._model_config.model

    def _temperature(self) -> float:
        if not self._model_config:
            self._model_config = self.config.get_model_config(self.default_model)
        return self._model_config.temperature

    async def run(self, prompt: str, context: str = "") -> Dict[str, Any]:
        raise NotImplementedError

    def _parse_json_response(self, content: str) -> dict:
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            if "```json" in content:
                start = content.index("```json") + 7
                end = content.index("```", start)
                return json.loads(content[start:end])
            return {"raw": content}


class SubagentResult:
    def __init__(self, success: bool, data: Any, error: Optional[str] = None):
        self.success = success
        self.data = data
        self.error = error

    def to_dict(self) -> dict:
        return {"success": self.success, "data": self.data, "error": self.error}
