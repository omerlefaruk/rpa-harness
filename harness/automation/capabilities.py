"""Typed capability contracts and application-facing adapters for retained RPA surfaces.

Capabilities never mutate the lifecycle graph. They return ToolResult values that the
AutomationApplication admits, verifies, and evidences.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Protocol

from harness.automation.application import (
    AutomationDefinition,
    ToolResult,
    WriteAdapter,
)
from harness.automation.authoring import AutomationAction, SelectorEvidence
from harness.security import SecretValue, redact_value

BROWSER_SELECTOR_PRIORITY = ("role", "label", "test_id", "css", "xpath", "coordinate")
DESKTOP_SELECTOR_PRIORITY = (
    "automation_id",
    "name",
    "class",
    "tree_path",
    "image",
    "coordinate",
)
WEAK_STRATEGIES = frozenset({"css", "xpath", "coordinate", "image"})

ACTION_CLASSES = {
    "navigate": "R0",
    "inspect": "R0",
    "extract": "R0",
    "wait": "R0",
    "screenshot": "R0",
    "download": "R1",
    "fill": "R3",
    "click": "R3",
    "api_get": "R0",
    "api_post": "R3",
    "api_put": "R3",
    "api_delete": "R3",
    "excel_read": "R0",
    "excel_write": "R3",
    "desktop_launch": "R1",
    "desktop_inspect": "R0",
    "desktop_read": "R0",
    "desktop_focus": "R1",
    "desktop_type": "R3",
    "desktop_select": "R3",
    "desktop_click": "R3",
    "desktop_capture": "R0",
}


@dataclass(frozen=True)
class CapabilityOp:
    name: str
    action_class: str
    read_only: bool
    inputs: Mapping[str, Any] = field(default_factory=dict)
    selector: SelectorEvidence | None = None
    success_check: str = ""


class BrowserPort(Protocol):
    def navigate(self, url: str) -> dict[str, Any]: ...
    def inspect(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def extract(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def fill(self, selector: SelectorEvidence, value: str) -> dict[str, Any]: ...
    def click(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def wait(self, condition: str) -> dict[str, Any]: ...
    def download(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def screenshot(self, name: str = "page") -> dict[str, Any]: ...


class ApiPort(Protocol):
    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]: ...


class ExcelPort(Protocol):
    def read_rows(self, path: str, sheet: str) -> dict[str, Any]: ...
    def write_rows(self, path: str, sheet: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]: ...


class DesktopPort(Protocol):
    def launch(self, app: str) -> dict[str, Any]: ...
    def inspect(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def read(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def focus(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def type_text(self, selector: SelectorEvidence, text: str) -> dict[str, Any]: ...
    def select(self, selector: SelectorEvidence, value: str) -> dict[str, Any]: ...
    def click(self, selector: SelectorEvidence) -> dict[str, Any]: ...
    def capture(self, name: str = "window") -> dict[str, Any]: ...


def mark_selector(selector: SelectorEvidence) -> dict[str, Any]:
    return {
        "strategy": selector.strategy,
        "locator": selector.locator,
        "verified": selector.verified,
        "weak": selector.strategy in WEAK_STRATEGIES,
        "priority_rank": _priority_rank(selector.strategy),
    }


def _priority_rank(strategy: str) -> int:
    if strategy in BROWSER_SELECTOR_PRIORITY:
        return BROWSER_SELECTOR_PRIORITY.index(strategy)
    if strategy in DESKTOP_SELECTOR_PRIORITY:
        return DESKTOP_SELECTOR_PRIORITY.index(strategy)
    return 99


def validate_selector_priority(selector: SelectorEvidence, *, surface: str) -> None:
    ladder = BROWSER_SELECTOR_PRIORITY if surface == "browser" else DESKTOP_SELECTOR_PRIORITY
    if selector.strategy not in ladder:
        raise ValueError(f"selector strategy {selector.strategy!r} not in {surface} priority ladder")
    if selector.strategy in WEAK_STRATEGIES and not selector.verified:
        raise ValueError("weak selector fallback requires verified=true and approval")


class CapabilityExecutor:
    """Maps capability ops to ToolResults without lifecycle authority."""

    def __init__(
        self,
        *,
        browser: BrowserPort | None = None,
        api: ApiPort | None = None,
        excel: ExcelPort | None = None,
        desktop: DesktopPort | None = None,
    ) -> None:
        self.browser = browser
        self.api = api
        self.excel = excel
        self.desktop = desktop

    def run(self, op: CapabilityOp, *, secrets: Mapping[str, SecretValue] | None = None) -> ToolResult:
        secrets = secrets or {}
        name = op.name
        if name in {
            "navigate",
            "inspect",
            "extract",
            "fill",
            "click",
            "wait",
            "download",
            "screenshot",
        }:
            return self._browser(op, secrets)
        if name.startswith("api_"):
            return self._api(op, secrets)
        if name.startswith("excel_"):
            return self._excel(op, secrets)
        if name.startswith("desktop_"):
            return self._desktop(op, secrets)
        raise ValueError(f"unknown capability operation: {name}")

    def as_read_adapter(self, op: CapabilityOp) -> Callable[[AutomationDefinition, str], ToolResult]:
        def adapter(_definition: AutomationDefinition, _run_id: str) -> ToolResult:
            return self.run(op)

        return adapter

    def as_write_adapter(self, op: CapabilityOp) -> WriteAdapter:
        def adapter(
            _definition: AutomationDefinition,
            _run_id: str,
            *,
            secrets: Mapping[str, SecretValue],
            action: AutomationAction | None,
        ) -> ToolResult:
            del action
            return self.run(op, secrets=secrets)

        return adapter

    def _browser(self, op: CapabilityOp, secrets: Mapping[str, SecretValue]) -> ToolResult:
        if self.browser is None:
            raise RuntimeError("browser port not configured")
        if op.selector is not None:
            validate_selector_priority(op.selector, surface="browser")
        port = self.browser
        if op.name == "navigate":
            raw = port.navigate(str(op.inputs["url"]))
        elif op.name == "inspect":
            assert op.selector is not None
            raw = port.inspect(op.selector)
        elif op.name == "extract":
            assert op.selector is not None
            raw = port.extract(op.selector)
        elif op.name == "fill":
            assert op.selector is not None
            value = self._materialize(op.inputs.get("value", ""), secrets)
            raw = port.fill(op.selector, value)
        elif op.name == "click":
            assert op.selector is not None
            raw = port.click(op.selector)
        elif op.name == "wait":
            raw = port.wait(str(op.inputs.get("condition", "stable")))
        elif op.name == "download":
            assert op.selector is not None
            raw = port.download(op.selector)
        else:
            raw = port.screenshot(str(op.inputs.get("name", "page")))
        return self._to_result(raw, selector=op.selector, kind="browser")

    def _api(self, op: CapabilityOp, secrets: Mapping[str, SecretValue]) -> ToolResult:
        if self.api is None:
            raise RuntimeError("api port not configured")
        method = op.name.removeprefix("api_").upper()
        headers = dict(op.inputs.get("headers") or {})
        for key, value in list(headers.items()):
            if isinstance(value, str) and value.startswith("${secrets."):
                headers[key] = self._materialize(value, secrets)
        raw = self.api.request(
            method,
            str(op.inputs["url"]),
            headers=headers,
            json=op.inputs.get("json"),
            params=op.inputs.get("params"),
        )
        return self._to_result(raw, kind="api")

    def _excel(self, op: CapabilityOp, secrets: Mapping[str, SecretValue]) -> ToolResult:
        del secrets
        if self.excel is None:
            raise RuntimeError("excel port not configured")
        path = str(op.inputs["path"])
        sheet = str(op.inputs.get("sheet", "Sheet1"))
        if op.name == "excel_read":
            raw = self.excel.read_rows(path, sheet)
        else:
            raw = self.excel.write_rows(path, sheet, list(op.inputs.get("rows") or ()))
        return self._to_result(raw, kind="excel")

    def _desktop(self, op: CapabilityOp, secrets: Mapping[str, SecretValue]) -> ToolResult:
        if self.desktop is None:
            raise RuntimeError("desktop port not configured")
        if op.selector is not None:
            validate_selector_priority(op.selector, surface="desktop")
        port = self.desktop
        if op.name == "desktop_launch":
            raw = port.launch(str(op.inputs["app"]))
        elif op.name == "desktop_inspect":
            assert op.selector is not None
            raw = port.inspect(op.selector)
        elif op.name == "desktop_read":
            assert op.selector is not None
            raw = port.read(op.selector)
        elif op.name == "desktop_focus":
            assert op.selector is not None
            raw = port.focus(op.selector)
        elif op.name == "desktop_type":
            assert op.selector is not None
            raw = port.type_text(op.selector, self._materialize(op.inputs.get("text", ""), secrets))
        elif op.name == "desktop_select":
            assert op.selector is not None
            raw = port.select(op.selector, str(op.inputs["value"]))
        elif op.name == "desktop_click":
            assert op.selector is not None
            raw = port.click(op.selector)
        else:
            raw = port.capture(str(op.inputs.get("name", "window")))
        return self._to_result(raw, selector=op.selector, kind="desktop")

    @staticmethod
    def _materialize(value: Any, secrets: Mapping[str, SecretValue]) -> str:
        text = str(value)
        if text.startswith("${secrets.") and text.endswith("}"):
            name = text[len("${secrets.") : -1]
            if name not in secrets:
                raise KeyError(f"Unknown secret handle: {name}")
            return secrets[name].reveal()
        return text

    @staticmethod
    def _to_result(
        raw: Mapping[str, Any],
        *,
        selector: SelectorEvidence | None = None,
        kind: str,
    ) -> ToolResult:
        evidence = {
            "kind": kind,
            "refs": redact_value(dict(raw.get("evidence_refs") or {})),
            "selector": mark_selector(selector) if selector else None,
        }
        # Large blobs stay as references only.
        value = {key: val for key, val in raw.items() if key != "evidence_refs"}
        outcome = raw.get("write_outcome")
        return ToolResult(
            value=dict(value),
            evidence=evidence,
            write_outcome=str(outcome) if outcome is not None else None,
        )


@dataclass
class FakeBrowser:
    pages: dict[str, Any] = field(default_factory=dict)
    writes: list[dict[str, Any]] = field(default_factory=list)
    fail_verify: bool = False
    unknown_write: bool = False

    def navigate(self, url: str) -> dict[str, Any]:
        self.pages["url"] = url
        return {"url": url, "evidence_refs": {"dom": "evidence/dom.json"}}

    def inspect(self, selector: SelectorEvidence) -> dict[str, Any]:
        return {
            "visible": True,
            "selector": selector.locator,
            "evidence_refs": {"ax": "evidence/ax.json"},
        }

    def extract(self, selector: SelectorEvidence) -> dict[str, Any]:
        return {
            "text": self.pages.get("field", "count:3"),
            "selector": selector.locator,
            "evidence_refs": {"dom": "evidence/dom.json"},
        }

    def fill(self, selector: SelectorEvidence, value: str) -> dict[str, Any]:
        if self.unknown_write:
            return {
                "selector": selector.locator,
                "write_outcome": "unknown",
                "evidence_refs": {"shot": "evidence/shot.png"},
            }
        self.writes.append({"op": "fill", "selector": selector.locator, "value": value})
        self.pages["field"] = value
        return {
            "filled": True,
            "selector": selector.locator,
            "write_outcome": "applied",
            "evidence_refs": {"shot": "evidence/shot.png"},
        }

    def click(self, selector: SelectorEvidence) -> dict[str, Any]:
        self.writes.append({"op": "click", "selector": selector.locator})
        return {
            "clicked": True,
            "selector": selector.locator,
            "write_outcome": "applied",
            "evidence_refs": {"shot": "evidence/shot.png"},
        }

    def wait(self, condition: str) -> dict[str, Any]:
        return {"waited": condition}

    def download(self, selector: SelectorEvidence) -> dict[str, Any]:
        return {
            "path": "downloads/file.bin",
            "selector": selector.locator,
            "evidence_refs": {"file": "evidence/file.bin"},
        }

    def screenshot(self, name: str = "page") -> dict[str, Any]:
        return {"evidence_refs": {"screenshot": f"evidence/{name}.png"}}


@dataclass
class FakeApi:
    calls: list[dict[str, Any]] = field(default_factory=list)

    def request(self, method: str, url: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append({"method": method, "url": url, **kwargs})
        if method == "GET":
            return {"status": 200, "json": {"count": 3}, "evidence_refs": {"body": "evidence/api.json"}}
        return {
            "status": 201,
            "json": {"ok": True},
            "write_outcome": "applied",
            "evidence_refs": {"body": "evidence/api.json"},
        }


@dataclass
class FakeExcel:
    sheets: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    writes: list[dict[str, Any]] = field(default_factory=list)

    def read_rows(self, path: str, sheet: str) -> dict[str, Any]:
        rows = self.sheets.get(f"{path}:{sheet}", [{"sku": "1", "qty": 3}])
        return {"rows": rows, "evidence_refs": {"sheet": f"evidence/{sheet}.json"}}

    def write_rows(self, path: str, sheet: str, rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
        key = f"{path}:{sheet}"
        self.sheets[key] = [dict(row) for row in rows]
        self.writes.append({"path": path, "sheet": sheet, "rows": list(rows)})
        return {
            "written": len(rows),
            "write_outcome": "applied",
            "evidence_refs": {"sheet": f"evidence/{sheet}.json"},
        }


@dataclass
class FakeDesktop:
    tree: dict[str, Any] = field(default_factory=dict)
    writes: list[dict[str, Any]] = field(default_factory=list)

    def launch(self, app: str) -> dict[str, Any]:
        self.tree["app"] = app
        return {"launched": app, "evidence_refs": {"window": "evidence/window.json"}}

    def inspect(self, selector: SelectorEvidence) -> dict[str, Any]:
        return {
            "exists": True,
            "selector": selector.locator,
            "evidence_refs": {"uia": "evidence/uia.json"},
        }

    def read(self, selector: SelectorEvidence) -> dict[str, Any]:
        return {
            "text": self.tree.get(selector.locator, "Ready"),
            "evidence_refs": {"uia": "evidence/uia.json"},
        }

    def focus(self, selector: SelectorEvidence) -> dict[str, Any]:
        return {"focused": selector.locator}

    def type_text(self, selector: SelectorEvidence, text: str) -> dict[str, Any]:
        self.writes.append({"op": "type", "selector": selector.locator, "text": text})
        self.tree[selector.locator] = text
        return {
            "typed": True,
            "write_outcome": "applied",
            "evidence_refs": {"shot": "evidence/desktop.png"},
        }

    def select(self, selector: SelectorEvidence, value: str) -> dict[str, Any]:
        self.writes.append({"op": "select", "selector": selector.locator, "value": value})
        return {"selected": value, "write_outcome": "applied"}

    def click(self, selector: SelectorEvidence) -> dict[str, Any]:
        self.writes.append({"op": "click", "selector": selector.locator})
        return {
            "clicked": True,
            "write_outcome": "applied",
            "evidence_refs": {"shot": "evidence/desktop.png"},
        }

    def capture(self, name: str = "window") -> dict[str, Any]:
        return {"evidence_refs": {"screenshot": f"evidence/{name}.png"}}
