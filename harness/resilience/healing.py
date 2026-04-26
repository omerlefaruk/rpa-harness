"""
Auto-healing selector engine.
Repairs broken selectors using variation ladder + AI vision fallback.
"""

import asyncio
from typing import Any, Callable, Dict, List, Optional, Tuple

from harness.selectors.strategies import generate_selector_variations, get_healing_ladder, score_selector


class SelectorHealer:
    def __init__(self, vision_engine=None):
        self._vision = vision_engine
        self._cache: Dict[str, List[Tuple[str, int]]] = {}

    async def heal(
        self,
        broken_selector: str,
        test_fn: Callable[[str], Any],
        element_description: str = "",
        element_type: str = "element",
        screenshot_fn: Optional[Callable[[], Any]] = None,
        timeout: float = 2.0,
    ) -> Optional[str]:
        """
        Heal a broken selector using a priority ladder.

        1. Try cached selectors for this description
        2. Try standard healing ladder variations
        3. Try generated selector variations from element description
        4. Fallback: AI vision to find element and generate selector
        """

        cached = self._cache.get(element_description, [])
        for cached_sel, _ in cached:
            try:
                result = await asyncio.wait_for(
                    asyncio.ensure_future(asyncio.to_thread(test_fn, cached_sel)),
                    timeout=timeout,
                )
                if result:
                    return cached_sel
            except (asyncio.TimeoutError, Exception):
                continue

        ladder = get_healing_ladder(broken_selector)
        for selector in ladder:
            try:
                result = await asyncio.wait_for(
                    asyncio.ensure_future(asyncio.to_thread(test_fn, selector)),
                    timeout=timeout,
                )
                if result:
                    self._cache_selector(element_description, selector)
                    return selector
            except (asyncio.TimeoutError, Exception):
                continue

        variations = generate_selector_variations(element_description, element_type)
        for selector in variations:
            try:
                result = await asyncio.wait_for(
                    asyncio.ensure_future(asyncio.to_thread(test_fn, selector)),
                    timeout=timeout,
                )
                if result:
                    self._cache_selector(element_description, selector)
                    return selector
            except (asyncio.TimeoutError, Exception):
                continue

        if self._vision and screenshot_fn:
            try:
                screenshot = await screenshot_fn()
                if screenshot:
                    healed = await self._heal_via_vision(screenshot, element_description)
                    if healed:
                        try:
                            await test_fn(healed)
                            self._cache_selector(element_description, healed)
                            return healed
                        except Exception:
                            pass
            except Exception:
                pass

        return None

    async def _heal_via_vision(self, screenshot_path: str, description: str) -> Optional[str]:
        try:
            element = await self._vision.find_element(screenshot_path, description)
            if element:
                return await self._vision.generate_selector(screenshot_path, description)
        except Exception:
            pass
        return None

    def _cache_selector(self, description: str, selector: str):
        score = score_selector(selector)
        if description not in self._cache:
            self._cache[description] = []
        self._cache[description].append((selector, score))
        self._cache[description].sort(key=lambda x: x[1], reverse=True)
        self._cache[description] = self._cache[description][:10]

    def get_cached_selector(self, description: str) -> Optional[str]:
        cached = self._cache.get(description, [])
        return cached[0][0] if cached else None

    def clear_cache(self):
        self._cache.clear()
