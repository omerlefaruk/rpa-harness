"""
AI Vision Engine for UI automation.
Provides visual element detection, state verification, and selector generation.
Supports OpenAI-compatible endpoints for flexible provider choice.
"""

import base64
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass

from harness.config import HarnessConfig
from harness.logger import HarnessLogger


@dataclass
class DetectedElement:
    label: str
    confidence: float
    bbox: Tuple[int, int, int, int]  # x, y, w, h
    center: Tuple[int, int]
    ocr_text: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "label": self.label,
            "confidence": self.confidence,
            "bbox": list(self.bbox),
            "center": list(self.center),
            "ocr_text": self.ocr_text,
        }


class VisionEngine:
    def __init__(self, config: Optional[HarnessConfig] = None):
        self.config = config
        self.logger = HarnessLogger("vision")
        self._client = None
        self._cache: Dict[str, Any] = {}

    def _get_client(self):
        if self._client is None:
            try:
                from openai import OpenAI
                kwargs = self.config.get_openai_client_kwargs() if self.config else {}
                self._client = OpenAI(**kwargs)
            except ImportError:
                self.logger.error("OpenAI package not installed for vision")
                raise
        return self._client

    def _model(self) -> str:
        if self.config and self.config.vision_model:
            return self.config.vision_model
        return "gpt-4o"

    async def analyze_screenshot(self, screenshot_path: str,
                                 query: Optional[str] = None) -> Dict[str, Any]:
        self.logger.info(f"Analyzing screenshot: {screenshot_path}")

        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        system_prompt = """You are a UI automation vision assistant.
Analyze the screenshot and return a JSON object with:
{
  "page_title": "...",
  "description": "Brief description",
  "elements": [
    {"type": "button|input|link|menu|text|table|dropdown|checkbox|radio",
     "label": "...",
     "location": "top-left|top|top-right|left|center|right|bottom-left|bottom|bottom-right",
     "selector_suggestion": "CSS selector or XPath hint",
     "text_content": "visible text if any"}
  ],
  "state": "login_page|dashboard|form|error|loading|search|list|detail|...",
  "suggested_next_action": "What to do next"
}"""

        user_prompt = query or "Analyze this UI screenshot and identify all interactive elements."

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model(),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{image_data}"}}
                    ]}
                ],
                temperature=self.config.vision_temperature if self.config else 0.2,
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            self.logger.info(f"Vision analysis complete: {result.get('state', 'unknown')}")
            return result
        except Exception as e:
            self.logger.error(f"Vision analysis failed: {e}")
            return {"error": str(e), "elements": []}

    async def find_element(self, screenshot_path: str,
                           description: str) -> Optional[DetectedElement]:
        self.logger.info(f"Vision find: {description}")

        with open(screenshot_path, "rb") as f:
            image_data = base64.b64encode(f.read()).decode("utf-8")

        prompt = f"""Find the element described as: "{description}"
Return a JSON object:
{{"found": true, "bbox": [x, y, width, height], "confidence": 0.95, "center": [cx, cy], "text": "visible text"}}
If not found: {{"found": false}}"""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model(),
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": f"data:image/png;base64,{image_data}"}}
                    ]
                }],
                temperature=0.1,
                max_tokens=500,
                response_format={"type": "json_object"},
            )

            result = json.loads(response.choices[0].message.content)
            if result.get("found"):
                bbox = result["bbox"]
                center = result.get("center", (bbox[0] + bbox[2] // 2, bbox[1] + bbox[3] // 2))
                return DetectedElement(
                    label=description,
                    confidence=result.get("confidence", 0.8),
                    bbox=tuple(bbox),
                    center=tuple(center),
                    ocr_text=result.get("text"),
                )
        except Exception as e:
            self.logger.error(f"Vision find failed: {e}")

        return None

    async def verify_state(self, screenshot_path: str,
                           expected_state: str) -> Tuple[bool, str]:
        self.logger.info(f"Vision verify: {expected_state}")

        analysis = await self.analyze_screenshot(screenshot_path)
        description = analysis.get("description", "").lower()
        state = analysis.get("state", "").lower()
        expected = expected_state.lower()

        passed = expected in description or expected in state
        reasoning = f"Detected: {state}. Description: {description[:200]}"

        return passed, reasoning

    async def compare_screenshots(self, baseline_path: str,
                                  current_path: str) -> Dict[str, Any]:
        self.logger.info("Comparing screenshots")

        with open(baseline_path, "rb") as f:
            baseline_b64 = base64.b64encode(f.read()).decode("utf-8")
        with open(current_path, "rb") as f:
            current_b64 = base64.b64encode(f.read()).decode("utf-8")

        prompt = """Compare two screenshots (baseline vs current).
Return JSON: {"identical": true|false, "differences": ["..."], "severity": "none|minor|major|critical"}"""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._model(),
                messages=[{"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{baseline_b64}"}},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{current_b64}"}}
                ]}],
                temperature=0.1,
                max_tokens=1000,
                response_format={"type": "json_object"},
            )
            return json.loads(response.choices[0].message.content)
        except Exception as e:
            self.logger.error(f"Comparison failed: {e}")
            return {"identical": False, "differences": [str(e)], "severity": "error"}

    async def generate_selector(self, screenshot_path: str,
                                element_description: str) -> Optional[str]:
        self.logger.info(f"Generating selector for: {element_description}")

        analysis = await self.analyze_screenshot(
            screenshot_path,
            f"Generate the best CSS selector, XPath, or test-id for: {element_description}"
        )

        elements = analysis.get("elements", [])
        for el in elements:
            if element_description.lower() in el.get("description", "").lower():
                return el.get("selector_suggestion")

        return None

    async def describe_page(self, screenshot_path: str) -> Dict[str, Any]:
        return await self.analyze_screenshot(screenshot_path, "Describe everything visible on this page")

    async def extract_all_inputs(self, screenshot_path: str) -> List[Dict[str, str]]:
        analysis = await self.analyze_screenshot(screenshot_path, "List all input fields, their labels, and suggested selectors")
        return [el for el in analysis.get("elements", []) if el.get("type") == "input"]

    async def extract_all_buttons(self, screenshot_path: str) -> List[Dict[str, str]]:
        analysis = await self.analyze_screenshot(screenshot_path, "List all buttons and their labels")
        return [el for el in analysis.get("elements", []) if el.get("type") == "button"]
