"""Real capability port adapters implementing BrowserPort/ApiPort/ExcelPort/DesktopPort.

These are thin, dependency-light adapters for production hosts. Agent loops and CI
should prefer Fake* ports via build_executor("fake_*"). Optional deps (playwright,
openpyxl, pywinauto, httpx) are imported lazily so test collection does not require
every driver install.
"""

from __future__ import annotations

import sys
import tempfile
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from harness.automation.authoring import SelectorEvidence


class HttpApiPort:
    """Sync httpx client implementing ApiPort.request."""

    def __init__(self, *, timeout: float = 30.0, base_url: str = "") -> None:
        self.timeout = timeout
        self.base_url = base_url.rstrip("/")
        self._client: Any = None

    def _get_client(self) -> Any:
        if self._client is None:
            import httpx

            self._client = httpx.Client(
                base_url=self.base_url or None,
                timeout=self.timeout,
                follow_redirects=True,
            )
        return self._client

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None

    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        client = self._get_client()
        allowed = {key: kwargs[key] for key in ("headers", "json", "params", "data", "content") if key in kwargs}
        response = client.request(method.upper(), url, **allowed)
        body_json: Any = None
        try:
            body_json = response.json()
        except Exception:
            body_json = None
        result: dict[str, Any] = {
            "status": response.status_code,
            "text": response.text,
            "evidence_refs": {
                "url": str(response.url),
                "status": response.status_code,
            },
        }
        if body_json is not None:
            result["json"] = body_json
        if method.upper() != "GET":
            result["write_outcome"] = (
                "applied" if 200 <= response.status_code < 300 else "unknown"
            )
        return result


class ExcelFilePort:
    """ExcelPort backed by harness.rpa.excel.ExcelHandler (openpyxl)."""

    def read_rows(self, path: str, sheet: str) -> dict[str, Any]:
        from harness.rpa.excel import ExcelHandler

        handler = ExcelHandler(path, create_if_missing=False)
        try:
            rows = [dict(row.data) for row in handler.iter_rows(sheet=sheet)]
            return {
                "rows": rows,
                "evidence_refs": {"sheet": str(path), "name": sheet},
            }
        finally:
            handler.close()

    def write_rows(
        self, path: str, sheet: str, rows: Sequence[Mapping[str, Any]]
    ) -> dict[str, Any]:
        from harness.rpa.excel import ExcelHandler

        handler = ExcelHandler(path, create_if_missing=True)
        try:
            material = [dict(row) for row in rows]
            if material:
                headers = list(material[0].keys())
                list_rows = [[row.get(header) for header in headers] for row in material]
                handler.write_rows(sheet=sheet, headers=headers, rows=list_rows)
            else:
                handler.create_sheet(sheet)
            handler.save()
            return {
                "written": len(material),
                "write_outcome": "applied",
                "evidence_refs": {"sheet": str(path), "name": sheet},
            }
        finally:
            handler.close()


class SyncPlaywrightBrowserPort:
    """BrowserPort using Playwright sync_api (lazy start)."""

    def __init__(
        self,
        *,
        headless: bool = True,
        browser_name: str = "chromium",
        evidence_dir: str | Path | None = None,
    ) -> None:
        self.headless = headless
        self.browser_name = browser_name
        self.evidence_dir = Path(evidence_dir) if evidence_dir else Path(tempfile.mkdtemp(prefix="rpa_browser_"))
        self._playwright: Any = None
        self._browser: Any = None
        self._context: Any = None
        self._page: Any = None

    def _ensure_page(self) -> Any:
        if self._page is not None:
            return self._page
        try:
            from playwright.sync_api import sync_playwright
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Playwright is not installed. Install with: "
                "pip install playwright && playwright install chromium"
            ) from exc
        self._playwright = sync_playwright().start()
        browser_type = getattr(self._playwright, self.browser_name)
        self._browser = browser_type.launch(headless=self.headless)
        self._context = self._browser.new_context()
        self._page = self._context.new_page()
        self.evidence_dir.mkdir(parents=True, exist_ok=True)
        return self._page

    def close(self) -> None:
        if self._context is not None:
            self._context.close()
            self._context = None
        if self._browser is not None:
            self._browser.close()
            self._browser = None
        if self._playwright is not None:
            self._playwright.stop()
            self._playwright = None
        self._page = None

    def _locator(self, page: Any, selector: SelectorEvidence) -> Any:
        strategy = selector.strategy
        locator = selector.locator
        if strategy == "role":
            # locator forms: "button:Save" or "button" or plain name
            if ":" in locator:
                role, name = locator.split(":", 1)
                return page.get_by_role(role.strip(), name=name.strip())
            return page.get_by_role(locator)
        if strategy == "label":
            return page.get_by_label(locator)
        if strategy == "test_id":
            return page.get_by_test_id(locator)
        if strategy == "css":
            return page.locator(locator)
        if strategy == "xpath":
            expr = locator if locator.startswith("xpath=") else f"xpath={locator}"
            return page.locator(expr)
        if strategy == "coordinate":
            # last-resort: "x,y" — caller still needs verified=true at capability layer
            return None
        # Fallback treat as CSS
        return page.locator(locator)

    def _parse_coordinate(self, locator: str) -> tuple[float, float]:
        parts = [part.strip() for part in locator.replace(" ", "").split(",")]
        if len(parts) != 2:
            raise ValueError(f"coordinate locator must be 'x,y', got {locator!r}")
        return float(parts[0]), float(parts[1])

    def navigate(self, url: str) -> dict[str, Any]:
        page = self._ensure_page()
        page.goto(url)
        return {"url": page.url, "evidence_refs": {"url": page.url}}

    def inspect(self, selector: SelectorEvidence) -> dict[str, Any]:
        page = self._ensure_page()
        if selector.strategy == "coordinate":
            x, y = self._parse_coordinate(selector.locator)
            return {
                "visible": True,
                "selector": selector.locator,
                "coordinate": [x, y],
                "evidence_refs": {"url": page.url},
            }
        loc = self._locator(page, selector)
        visible = loc.is_visible()
        return {
            "visible": visible,
            "selector": selector.locator,
            "evidence_refs": {"url": page.url, "strategy": selector.strategy},
        }

    def extract(self, selector: SelectorEvidence) -> dict[str, Any]:
        page = self._ensure_page()
        if selector.strategy == "coordinate":
            raise ValueError("extract does not support coordinate strategy")
        loc = self._locator(page, selector)
        text = loc.inner_text()
        return {
            "text": text,
            "selector": selector.locator,
            "evidence_refs": {"url": page.url},
        }

    def fill(self, selector: SelectorEvidence, value: str) -> dict[str, Any]:
        page = self._ensure_page()
        if selector.strategy == "coordinate":
            raise ValueError("fill does not support coordinate strategy")
        loc = self._locator(page, selector)
        loc.fill(value)
        return {
            "filled": True,
            "selector": selector.locator,
            "write_outcome": "applied",
            "evidence_refs": {"url": page.url},
        }

    def click(self, selector: SelectorEvidence) -> dict[str, Any]:
        page = self._ensure_page()
        if selector.strategy == "coordinate":
            x, y = self._parse_coordinate(selector.locator)
            page.mouse.click(x, y)
        else:
            loc = self._locator(page, selector)
            loc.click()
        return {
            "clicked": True,
            "selector": selector.locator,
            "write_outcome": "applied",
            "evidence_refs": {"url": page.url},
        }

    def wait(self, condition: str) -> dict[str, Any]:
        page = self._ensure_page()
        # condition is free-form; support load states and generic timeout
        if condition in {"load", "domcontentloaded", "networkidle", "commit"}:
            page.wait_for_load_state(condition)
        elif condition.startswith("selector:"):
            page.wait_for_selector(condition.removeprefix("selector:"))
        else:
            page.wait_for_timeout(250)
        return {"waited": condition, "evidence_refs": {"url": page.url}}

    def download(self, selector: SelectorEvidence) -> dict[str, Any]:
        page = self._ensure_page()
        if selector.strategy == "coordinate":
            raise ValueError("download does not support coordinate strategy")
        loc = self._locator(page, selector)
        with page.expect_download() as download_info:
            loc.click()
        download = download_info.value
        target = self.evidence_dir / (download.suggested_filename or "download.bin")
        download.save_as(str(target))
        return {
            "path": str(target),
            "selector": selector.locator,
            "evidence_refs": {"file": str(target)},
        }

    def screenshot(self, name: str = "page") -> dict[str, Any]:
        page = self._ensure_page()
        path = self.evidence_dir / f"{name}.png"
        page.screenshot(path=str(path))
        return {"evidence_refs": {"screenshot": str(path)}}


class DesktopUiaPort:
    """Best-effort DesktopPort using sync pywinauto UIA when available.

    WindowsUIDriver is async-only; this adapter uses pywinauto's synchronous API
    directly. On non-Windows platforms or missing optional deps, methods raise
    RuntimeError without breaking import of this module.
    """

    def __init__(self, *, allow_coordinate_fallback: bool = False) -> None:
        self.allow_coordinate_fallback = allow_coordinate_fallback
        self._app: Any = None
        self._window: Any = None
        self._desktop: Any = None
        self._tree: dict[str, Any] = {}

    def _require_pywinauto(self) -> Any:
        if not sys.platform.startswith("win"):
            raise RuntimeError("desktop driver not available: Windows required")
        try:
            import pywinauto
        except ImportError as exc:
            raise RuntimeError(
                "desktop driver not available: install pywinauto (pip install pywinauto)"
            ) from exc
        return pywinauto

    def launch(self, app: str) -> dict[str, Any]:
        pywinauto = self._require_pywinauto()
        from pywinauto import Application, Desktop

        self._app = Application(backend="uia").start(app)
        self._desktop = Desktop(backend="uia")
        self._tree["app"] = app
        try:
            self._app.wait_cpu_usage_lower(threshold=5, timeout=15)
        except Exception:
            pass
        try:
            self._window = self._app.top_window()
        except Exception:
            self._window = None
        return {
            "launched": app,
            "evidence_refs": {"window": "desktop/window", "backend": "uia"},
        }

    def _find(self, selector: SelectorEvidence) -> Any:
        self._require_pywinauto()
        root = self._window or self._desktop
        if root is None:
            raise RuntimeError("desktop driver not available: no launched/attached window")
        strategy = selector.strategy
        locator = selector.locator
        criteria: dict[str, Any] = {}
        if strategy == "automation_id":
            criteria["auto_id"] = locator
        elif strategy == "name":
            # optional "Name|ControlType"
            if "|" in locator:
                name, control_type = locator.split("|", 1)
                criteria["title"] = name
                criteria["control_type"] = control_type
            else:
                criteria["title"] = locator
        elif strategy == "class":
            if "|" in locator:
                class_name, control_type = locator.split("|", 1)
                criteria["class_name"] = class_name
                criteria["control_type"] = control_type
            else:
                criteria["class_name"] = locator
        elif strategy == "tree_path":
            # path like "Pane>Button:OK" — best-effort title search on last segment
            leaf = locator.split(">")[-1]
            if ":" in leaf:
                _, title = leaf.split(":", 1)
                criteria["title"] = title
            else:
                criteria["title"] = leaf
        elif strategy == "coordinate":
            return None
        elif strategy == "image":
            raise RuntimeError("desktop image strategy is not implemented in DesktopUiaPort")
        else:
            criteria["title"] = locator
        return root.child_window(**criteria)

    def inspect(self, selector: SelectorEvidence) -> dict[str, Any]:
        if selector.strategy == "coordinate":
            return {
                "exists": True,
                "selector": selector.locator,
                "evidence_refs": {"uia": "coordinate"},
            }
        el = self._find(selector)
        exists = bool(el.exists(timeout=2)) if el is not None else False
        return {
            "exists": exists,
            "selector": selector.locator,
            "evidence_refs": {"uia": selector.strategy},
        }

    def read(self, selector: SelectorEvidence) -> dict[str, Any]:
        if selector.strategy == "coordinate":
            raise ValueError("read does not support coordinate strategy")
        el = self._find(selector)
        el.wait("exists", timeout=5)
        text = el.window_text()
        self._tree[selector.locator] = text
        return {"text": text, "evidence_refs": {"uia": selector.strategy}}

    def focus(self, selector: SelectorEvidence) -> dict[str, Any]:
        if selector.strategy == "coordinate":
            raise ValueError("focus does not support coordinate strategy")
        el = self._find(selector)
        el.set_focus()
        return {"focused": selector.locator, "evidence_refs": {"uia": selector.strategy}}

    def type_text(self, selector: SelectorEvidence, text: str) -> dict[str, Any]:
        if selector.strategy == "coordinate":
            raise ValueError("type_text does not support coordinate strategy")
        el = self._find(selector)
        el.set_focus()
        el.type_keys(text, with_spaces=True)
        self._tree[selector.locator] = text
        return {
            "typed": True,
            "write_outcome": "applied",
            "evidence_refs": {"uia": selector.strategy},
        }

    def select(self, selector: SelectorEvidence, value: str) -> dict[str, Any]:
        if selector.strategy == "coordinate":
            raise ValueError("select does not support coordinate strategy")
        el = self._find(selector)
        el.select(value)
        return {
            "selected": value,
            "write_outcome": "applied",
            "evidence_refs": {"uia": selector.strategy},
        }

    def click(self, selector: SelectorEvidence) -> dict[str, Any]:
        if selector.strategy == "coordinate":
            if not self.allow_coordinate_fallback:
                raise RuntimeError(
                    "coordinate desktop click requires allow_coordinate_fallback=True"
                )
            from pywinauto import mouse

            x, y = [int(float(p.strip())) for p in selector.locator.split(",")]
            mouse.click(coords=(x, y))
            return {
                "clicked": True,
                "write_outcome": "applied",
                "evidence_refs": {"uia": "coordinate"},
            }
        el = self._find(selector)
        el.click_input()
        return {
            "clicked": True,
            "write_outcome": "applied",
            "evidence_refs": {"uia": selector.strategy},
        }

    def capture(self, name: str = "window") -> dict[str, Any]:
        self._require_pywinauto()
        target = Path(tempfile.mkdtemp(prefix="rpa_desktop_")) / f"{name}.png"
        if self._window is not None:
            img = self._window.capture_as_image()
            img.save(str(target))
        return {"evidence_refs": {"screenshot": str(target)}}
