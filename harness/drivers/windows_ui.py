"""
Windows UI Automation driver using pywinauto UIA backend.
Supports app launch, element discovery, interaction, and screenshot capture.
"""

import asyncio
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from harness.config import HarnessConfig
from harness.drivers.base import AbstractBaseDriver
from harness.logger import HarnessLogger


@dataclass
class UIElement:
    name: Optional[str] = None
    automation_id: Optional[str] = None
    class_name: Optional[str] = None
    control_type: Optional[str] = None
    text: Optional[str] = None
    rect: Optional[Tuple[int, int, int, int]] = None
    is_enabled: bool = True
    is_visible: bool = True
    children: List["UIElement"] = None
    native_element: Any = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "automation_id": self.automation_id,
            "class_name": self.class_name,
            "control_type": self.control_type,
            "text": self.text,
            "rect": self.rect,
            "is_enabled": self.is_enabled,
            "is_visible": self.is_visible,
        }


class WindowsUIDriver(AbstractBaseDriver):
    driver_type = "windows_ui"

    def __init__(self, config: Optional[HarnessConfig] = None):
        super().__init__(config)
        self._app = None
        self._app_name: Optional[str] = None
        self._window = None
        self._desktop = None
        self._pywinauto = None

        if sys.platform.startswith("win"):
            try:
                import pywinauto
                self._pywinauto = pywinauto
            except ImportError:
                self.logger.warning("pywinauto not installed. Windows automation unavailable.")
        else:
            self.logger.warning("WindowsUIDriver only supports Windows. Platform: " + sys.platform)

    async def launch(self, **kwargs):
        pass

    async def launch_app(self, app_path: str, app_name: Optional[str] = None,
                         wait_for_window: bool = True, timeout: int = 30):
        if not self._pywinauto:
            raise RuntimeError("pywinauto not available")

        self._app_name = app_name or app_path
        self.logger.info(f"Launching: {self._app_name}")

        from pywinauto import Application, Desktop
        self._app = Application(backend="uia").start(app_path)
        self._desktop = Desktop(backend="uia")

        if wait_for_window:
            await asyncio.to_thread(
                self._app.wait_cpu_usage_lower, threshold=5, timeout=timeout
            )

        self._connected = True

    async def connect_to_app(self, title: str = None, class_name: str = None, timeout: int = 10):
        from pywinauto import Desktop
        self._desktop = Desktop(backend="uia")

        criteria = {}
        if title:
            criteria["title_re"] = f".*{title}.*"
        if class_name:
            criteria["class_name"] = class_name

        self._window = self._desktop.window(**criteria)
        if self._window:
            await asyncio.to_thread(self._window.wait, "visible", timeout)
            self._connected = True
            self.logger.info(f"Connected to window: {title or class_name}")

    async def click(self, name: Optional[str] = None, automation_id: Optional[str] = None,
                    class_name: Optional[str] = None, control_type: Optional[str] = None,
                    coordinates: Optional[Tuple[int, int]] = None, timeout: int = 10):
        self.logger.info(f"Click: name={name}, id={automation_id}")

        if coordinates:
            await self._click_at(*coordinates)
            return

        el = await self.find_element(name=name, automation_id=automation_id,
                                     class_name=class_name, control_type=control_type,
                                     timeout=timeout)
        if el and el.native_element:
            await asyncio.to_thread(el.native_element.click_input)

    async def double_click(self, name: Optional[str] = None,
                           automation_id: Optional[str] = None, timeout: int = 10):
        el = await self.find_element(name=name, automation_id=automation_id, timeout=timeout)
        if el and el.native_element:
            await asyncio.to_thread(el.native_element.double_click_input)

    async def right_click(self, name: Optional[str] = None,
                          automation_id: Optional[str] = None, timeout: int = 10):
        el = await self.find_element(name=name, automation_id=automation_id, timeout=timeout)
        if el and el.native_element:
            await asyncio.to_thread(el.native_element.right_click_input)

    async def type_keys(self, text: str, with_spaces: bool = True,
                        name: Optional[str] = None, automation_id: Optional[str] = None,
                        timeout: int = 10):
        self.logger.info(f"Typing: '{text[:50]}'")
        el = None
        if name or automation_id:
            el = await self.find_element(name=name, automation_id=automation_id, timeout=timeout)

        if el and el.native_element:
            await asyncio.to_thread(el.native_element.type_keys, text, with_spaces=with_spaces)
        else:
            import pyautogui
            pyautogui.typewrite(text, interval=0.01)

    async def press_keys(self, keys: str):
        import pyautogui
        pyautogui.hotkey(*keys.split("+"))

    async def get_text(self, name: Optional[str] = None,
                       automation_id: Optional[str] = None,
                       class_name: Optional[str] = None, timeout: int = 10) -> Optional[str]:
        el = await self.find_element(name=name, automation_id=automation_id,
                                     class_name=class_name, timeout=timeout)
        if el and el.native_element:
            try:
                return await asyncio.to_thread(el.native_element.window_text)
            except Exception:
                pass
        return None

    async def find_element(self, name: Optional[str] = None,
                           automation_id: Optional[str] = None,
                           class_name: Optional[str] = None,
                           control_type: Optional[str] = None,
                           timeout: int = 10) -> Optional[UIElement]:
        target = self._window or self._desktop
        if not target:
            return None

        start = time.time()
        while time.time() - start < timeout:
            try:
                kwargs = {}
                if name:
                    kwargs["title"] = name
                if automation_id:
                    kwargs["auto_id"] = automation_id
                if class_name:
                    kwargs["class_name"] = class_name
                if control_type:
                    kwargs["control_type"] = control_type

                el = await asyncio.to_thread(target.child_window, **kwargs)
                if await asyncio.to_thread(el.exists, timeout=1):
                    rect = await asyncio.to_thread(el.rectangle)
                    return UIElement(
                        name=name,
                        automation_id=automation_id,
                        class_name=class_name,
                        control_type=control_type,
                        rect=(rect.left, rect.top, rect.width(), rect.height()),
                        native_element=el,
                    )
            except Exception:
                pass
            time.sleep(0.5)
        return None

    async def find_elements(self, control_type: Optional[str] = None,
                            class_name: Optional[str] = None) -> List[UIElement]:
        target = self._window or self._desktop
        if not target:
            return []

        kwargs = {}
        if control_type:
            kwargs["control_type"] = control_type
        if class_name:
            kwargs["class_name"] = class_name

        elements = []
        try:
            descendants = await asyncio.to_thread(target.descendants)
            for el in descendants:
                match = True
                if control_type and getattr(el, "element_info", None):
                    if getattr(el.element_info, "control_type", "") != control_type:
                        match = False
                if class_name and getattr(el, "class_name", "") != class_name:
                    match = False
                if match:
                    rect = await asyncio.to_thread(el.rectangle)
                    elements.append(UIElement(
                        name=getattr(el, "window_text", lambda: "")(),
                        automation_id=getattr(el, "automation_id", ""),
                        class_name=getattr(el, "class_name", ""),
                        control_type=control_type,
                        rect=(rect.left, rect.top, rect.width(), rect.height()) if hasattr(rect, 'left') else None,
                        native_element=el,
                    ))
        except Exception as e:
            self.logger.warning(f"Element enumeration failed: {e}")

        return elements

    async def dump_tree(self, max_depth: int = 3) -> Dict[str, Any]:
        target = self._window or self._desktop
        if not target:
            return {}

        def _dump(el, depth=0):
            if depth > max_depth:
                return {"name": getattr(el, "window_text", lambda: "")()[:60], "_truncated": True}

            children = []
            try:
                for child in el.children():
                    children.append(_dump(child, depth + 1))
            except Exception:
                pass

            return {
                "name": getattr(el, "window_text", lambda: "")()[:60],
                "class": getattr(el, "class_name", lambda: "")()[:40],
                "auto_id": getattr(el, "automation_id", lambda: "")()[:40],
                "control_type": getattr(el.element_info, "control_type", "") if hasattr(el, "element_info") else "",
                "children": children[:50],
            }

        return await asyncio.to_thread(_dump, target)

    async def screenshot(self, name: Optional[str] = None) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = name or f"desktop_{ts}.png"
        report_dir = self.config.report_dir if self.config else "./reports"
        path = Path(report_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        from PIL import ImageGrab
        ImageGrab.grab().save(str(path))

        self._screenshots.append(str(path))
        self.logger.info(f"Screenshot: {path}")
        return str(path)

    async def close_app(self):
        self.logger.info("Closing application")
        if self._app:
            try:
                await asyncio.to_thread(self._app.kill)
            except Exception:
                pass
        self._connected = False

    async def close(self):
        await self.close_app()

    async def _click_at(self, x: int, y: int):
        import pyautogui
        pyautogui.click(x, y)
