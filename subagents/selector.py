"""
Selector subagent — browser reconnaissance and selector discovery.
Uses fast model for efficient page inspection.
Navigates, takes screenshots, inspects DOM, discovers selectors.
"""

from typing import Any, Dict, List, Optional

from harness.config import HarnessConfig
from harness.logger import HarnessLogger
from subagents.base import BaseSubagent, SubagentResult


class SelectorSubagent(BaseSubagent):
    subagent_name = "selector"
    default_model = "fast"

    def __init__(self, config: Optional[HarnessConfig] = None, playwright_driver=None):
        super().__init__(config)
        self.driver = playwright_driver

    async def run(self, prompt: str, context: str = "") -> SubagentResult:
        self.logger.info(f"Selector task: {prompt[:100]}")

        try:
            results: Dict[str, Any] = {}

            if self.driver:
                url = self._extract_url(prompt)
                if url:
                    await self.driver.goto(url, wait_until="networkidle")
                    current_url = await self.driver.get_url()
                    title = await self.driver.get_title()
                    results["url"] = current_url
                    results["title"] = title

                    screenshot = await self.driver.screenshot(name="selector_inspect.png")
                    results["screenshot"] = screenshot

                    content = await self.driver.get_content()
                    results["html_length"] = len(content)
                    results["html_snippet"] = content[:3000]

            client = self._get_client()
            system = """You are a selector discovery subagent.
Analyze HTML content and screenshots to find stable, reliable selectors.

Return JSON:
{
  "page_title": "...",
  "url": "...",
  "selectors": [
    {"element": "login button", "selector": "button[type='submit']", "stability": "high", "type": "css"},
    {"element": "username input", "selector": "#username", "stability": "high", "type": "css"},
    {"element": "price display", "selector": "[data-testid='price']", "stability": "very_high", "type": "css"}
  ],
  "dynamic_elements": ["List of elements that appear dynamic"],
  "suggestions": ["How to improve selector stability"]
}

Prefer in order: data-testid > aria-label > name > id > :has-text() > class
Avoid: nth-child, :first, dynamic IDs"""

            user = f"Task: {prompt}"
            if results.get("html_snippet"):
                user += f"\n\nHTML Snippet:\n{results['html_snippet'][:4000]}"
            if context:
                user += f"\n\nContext: {context}"

            response = client.chat.completions.create(
                model=self._model(),
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                temperature=self._temperature(),
                max_tokens=2000,
                response_format={"type": "json_object"},
            )

            data = self._parse_json_response(response.choices[0].message.content)
            results.update(data)
            self.logger.info(f"Selector found {len(data.get('selectors', []))} selectors")
            return SubagentResult(success=True, data=results)

        except Exception as e:
            self.logger.error(f"Selector failed: {e}")
            return SubagentResult(success=False, data={}, error=str(e))

    @staticmethod
    def _extract_url(prompt: str) -> Optional[str]:
        words = prompt.split()
        for word in words:
            if word.startswith("http://") or word.startswith("https://"):
                return word
        return None
