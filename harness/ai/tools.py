"""
Tool registry for the agentic AI loop.
Registers all available tools as OpenAI function-calling schema
with async handler functions.
"""

from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, field

from harness.logger import HarnessLogger


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    handler: Callable
    category: str = "general"
    requires_approval: bool = False

    def to_openai_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            }
        }


class ToolRegistry:
    def __init__(self, logger: Optional[HarnessLogger] = None):
        self.logger = logger or HarnessLogger("tools")
        self._tools: Dict[str, Tool] = {}

    def register(self, tool: Tool):
        self._tools[tool.name] = tool
        self.logger.debug(f"Registered tool: {tool.name}")

    def register_many(self, tools: List[Tool]):
        for tool in tools:
            self.register(tool)

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list(self, category: Optional[str] = None) -> List[Tool]:
        tools = list(self._tools.values())
        if category:
            tools = [t for t in tools if t.category == category]
        return tools

    def to_openai_schemas(self, category: Optional[str] = None) -> List[dict]:
        return [t.to_openai_schema() for t in self.list(category)]

    async def execute(self, name: str, arguments: dict) -> Any:
        tool = self._tools.get(name)
        if not tool:
            raise ValueError(f"Unknown tool: {name}")

        self.logger.info(f"Tool call: {name}({', '.join(f'{k}={str(v)[:40]}' for k, v in arguments.items())})")

        try:
            result = await tool.handler(**arguments)
            self.logger.debug(f"Tool result: {name} → {str(result)[:100]}")
            return result
        except Exception as e:
            self.logger.error(f"Tool execution failed: {name} — {e}")
            raise


def build_default_tools(
    playwright_driver=None,
    windows_driver=None,
    api_driver=None,
    excel_handler=None,
    vision_engine=None,
    memory_engine=None,
) -> List[Tool]:

    tools = []

    # Browser tools
    if playwright_driver:
        tools.extend([
            Tool(
                name="browser_navigate",
                description="Navigate to a URL in the browser",
                parameters={
                    "type": "object",
                    "properties": {
                        "url": {"type": "string", "description": "The full URL to navigate to"},
                        "wait_until": {
                            "type": "string",
                            "enum": ["networkidle", "load", "domcontentloaded"],
                            "description": "Wait condition after navigation",
                        },
                    },
                    "required": ["url"],
                },
                handler=playwright_driver.goto,
                category="browser",
            ),
            Tool(
                name="browser_click",
                description="Click a visible element by CSS selector",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector, XPath, or text selector"},
                        "timeout": {"type": "integer", "description": "Timeout in ms"},
                    },
                    "required": ["selector"],
                },
                handler=playwright_driver.click,
                category="browser",
            ),
            Tool(
                name="browser_fill",
                description="Fill a text input field",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector for input"},
                        "value": {"type": "string", "description": "Value to type"},
                    },
                    "required": ["selector", "value"],
                },
                handler=playwright_driver.fill,
                category="browser",
            ),
            Tool(
                name="browser_get_text",
                description="Get visible text from an element",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector for element"},
                    },
                    "required": ["selector"],
                },
                handler=playwright_driver.get_text,
                category="browser",
            ),
            Tool(
                name="browser_screenshot",
                description="Take a screenshot of the current page",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Optional filename"},
                        "full_page": {"type": "boolean", "description": "Capture full page scroll"},
                    },
                    "required": [],
                },
                handler=playwright_driver.screenshot,
                category="browser",
            ),
            Tool(
                name="browser_is_visible",
                description="Check if an element is visible on the page",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector"},
                        "timeout": {"type": "integer", "description": "Timeout in ms"},
                    },
                    "required": ["selector"],
                },
                handler=playwright_driver.is_visible,
                category="browser",
            ),
            Tool(
                name="browser_select_option",
                description="Select an option from a dropdown",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector for select element"},
                        "value": {"type": "string", "description": "Value or label to select"},
                    },
                    "required": ["selector", "value"],
                },
                handler=playwright_driver.select_option,
                category="browser",
            ),
            Tool(
                name="browser_extract_data",
                description="Extract structured data from the page using a schema mapping",
                parameters={
                    "type": "object",
                    "properties": {
                        "schema": {
                            "type": "object",
                            "description": "Mapping of field names to CSS selectors",
                        },
                    },
                    "required": ["schema"],
                },
                handler=playwright_driver.extract_data,
                category="browser",
            ),
            Tool(
                name="browser_extract_table",
                description="Extract table data from a table element",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector for the table element"},
                    },
                    "required": ["selector"],
                },
                handler=playwright_driver.extract_table,
                category="browser",
            ),
            Tool(
                name="browser_wait_for",
                description="Wait for an element to appear or become visible",
                parameters={
                    "type": "object",
                    "properties": {
                        "selector": {"type": "string", "description": "CSS selector to wait for"},
                        "timeout": {"type": "integer", "description": "Timeout in ms"},
                    },
                    "required": ["selector"],
                },
                handler=playwright_driver.wait_for,
                category="browser",
            ),
        ])

    # Desktop tools
    if windows_driver:
        tools.extend([
            Tool(
                name="desktop_click",
                description="Click a Windows UI element by name or automation ID",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Element name/title"},
                        "automation_id": {"type": "string", "description": "Automation ID"},
                        "class_name": {"type": "string", "description": "Class name"},
                    },
                    "required": [],
                },
                handler=windows_driver.click,
                category="desktop",
            ),
            Tool(
                name="desktop_type",
                description="Type text into the focused or named element",
                parameters={
                    "type": "object",
                    "properties": {
                        "text": {"type": "string", "description": "Text to type"},
                        "name": {"type": "string", "description": "Optional target element name"},
                    },
                    "required": ["text"],
                },
                handler=windows_driver.type_keys,
                category="desktop",
            ),
            Tool(
                name="desktop_get_text",
                description="Get text from a Windows UI element",
                parameters={
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Element name"},
                        "automation_id": {"type": "string", "description": "Automation ID"},
                    },
                    "required": [],
                },
                handler=windows_driver.get_text,
                category="desktop",
            ),
            Tool(
                name="desktop_screenshot",
                description="Take a screenshot of the desktop",
                parameters={
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
                handler=windows_driver.screenshot,
                category="desktop",
            ),
            Tool(
                name="desktop_dump_tree",
                description="Dump the UIA element tree for the current window",
                parameters={
                    "type": "object",
                    "properties": {
                        "max_depth": {"type": "integer", "description": "Max tree depth"},
                    },
                    "required": [],
                },
                handler=windows_driver.dump_tree,
                category="desktop",
            ),
        ])

    # API tools
    if api_driver:
        tools.extend([
            Tool(
                name="api_call",
                description="Make an HTTP API call",
                parameters={
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "enum": ["GET", "POST", "PUT", "PATCH", "DELETE"],
                        },
                        "path": {"type": "string", "description": "URL path or full URL"},
                        "json_data": {"type": "object", "description": "JSON body for POST/PUT"},
                        "params": {"type": "object", "description": "Query parameters"},
                    },
                    "required": ["method", "path"],
                },
                handler=lambda method, path, json_data=None, params=None:
                    getattr(api_driver, method.lower())(path, json_data=json_data, params=params),
                category="api",
            ),
        ])

    # Vision tools
    if vision_engine:
        tools.extend([
            Tool(
                name="vision_find_element",
                description="Find a UI element in a screenshot by visual description",
                parameters={
                    "type": "object",
                    "properties": {
                        "screenshot_path": {"type": "string", "description": "Path to screenshot"},
                        "description": {"type": "string", "description": "Visual description of the element"},
                    },
                    "required": ["screenshot_path", "description"],
                },
                handler=vision_engine.find_element,
                category="ai",
            ),
            Tool(
                name="vision_analyze",
                description="Analyze a screenshot and return all interactive elements",
                parameters={
                    "type": "object",
                    "properties": {
                        "screenshot_path": {"type": "string", "description": "Path to screenshot"},
                    },
                    "required": ["screenshot_path"],
                },
                handler=vision_engine.analyze_screenshot,
                category="ai",
            ),
            Tool(
                name="vision_verify",
                description="Verify the UI is in an expected state",
                parameters={
                    "type": "object",
                    "properties": {
                        "screenshot_path": {"type": "string", "description": "Path to screenshot"},
                        "expected_state": {"type": "string", "description": "Expected UI state description"},
                    },
                    "required": ["screenshot_path", "expected_state"],
                },
                handler=vision_engine.verify_state,
                category="ai",
            ),
        ])

    # Memory tools
    if memory_engine:
        tools.extend([
            Tool(
                name="memory_search",
                description="Search memory for past selectors, workflows, or patterns",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "search_type": {"type": "string", "enum": ["selector", "workflow", "error", "all"]},
                        "limit": {"type": "integer", "description": "Max results"},
                    },
                    "required": ["query"],
                },
                handler=memory_engine.search,
                category="memory",
            ),
        ])

    # Utility tools
    tools.extend([
        Tool(
            name="wait",
            description="Wait for a specified number of seconds",
            parameters={
                "type": "object",
                "properties": {
                    "seconds": {"type": "number", "description": "Number of seconds to wait"},
                },
                "required": ["seconds"],
            },
            handler=lambda seconds: __import__("asyncio").sleep(seconds),
            category="utility",
        ),
        Tool(
            name="done",
            description="Signal that the task is complete with a summary",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Summary of what was accomplished"},
                    "status": {"type": "string", "enum": ["success", "partial", "failed"]},
                },
                "required": ["summary", "status"],
            },
            handler=lambda summary, status: {"summary": summary, "status": status},
            category="utility",
        ),
    ])

    return tools
