"""
Memory context injection — formats memory search results
into structured context for agent steps.
"""

from typing import Any, Dict, List, Optional


class ContextInjector:
    def __init__(self, memory_search=None):
        self.search = memory_search

    async def inject(self, query: str, max_items: int = 5) -> Optional[str]:
        results = self.search.search_index(query, search_type="all", limit=max_items) if self.search else []
        if not results:
            return None

        lines = ["## Relevant past context:"]
        for r in results:
            if r.get("type") == "selector":
                lines.append(
                    f"- Cached selector: `{r.get('selector', '')}` "
                    f"(success rate: {r.get('rate', 0):.0%})"
                )
            elif r.get("type") == "observation":
                status = "pass" if r.get("success") else "fail"
                lines.append(
                    f"- Previous step [{status}]: {r.get('step', '')[:80]}"
                )
            elif r.get("type") == "error_pattern":
                lines.append(
                    f"- Known error: {r.get('signature', '')[:60]} "
                    f"({r.get('category', '')})"
                )

        return "\n".join(lines)

    async def inject_selectors(self, url_pattern: str, max_items: int = 5) -> Optional[str]:
        results = self.search.search_index(url_pattern, search_type="selector", limit=max_items) if self.search else []
        if not results:
            return None

        lines = ["## Cached selectors for this page:"]
        for r in results:
            lines.append(
                f"- `{r.get('selector', '')}` "
                f"(success rate: {r.get('rate', 0):.0%})"
            )

        return "\n".join(lines)

    async def inject_errors(self, error_description: str, max_items: int = 3) -> Optional[str]:
        results = self.search.search_index(error_description, search_type="error", limit=max_items) if self.search else []
        if not results:
            return None

        lines = ["## Known error patterns:"]
        for r in results:
            lines.append(
                f"- {r.get('signature', '')[:60]} "
                f"({r.get('category', '')})"
            )

        return "\n".join(lines)
