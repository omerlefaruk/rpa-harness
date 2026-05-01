"""
HTTP REST API driver for RPA API integrations.
Uses httpx async client with retry, auth, and JSON handling.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import httpx

from harness.config import HarnessConfig
from harness.drivers.base import AbstractBaseDriver
from harness.logger import HarnessLogger
from harness.security import sanitize_url


class APIDriver(AbstractBaseDriver):
    driver_type = "api"

    def __init__(self, config: Optional[HarnessConfig] = None, base_url: str = "",
                 headers: Optional[Dict[str, str]] = None, timeout: int = 30):
        super().__init__(config)
        self.base_url = base_url.rstrip("/")
        self._headers = headers or {}
        self._timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None
        self._last_response: Optional[httpx.Response] = None

    async def launch(self, **kwargs):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers,
            timeout=self._timeout,
            follow_redirects=True,
        )
        self._connected = True
        self.logger.info(f"API client ready: {self.base_url}")

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def screenshot(self, name: Optional[str] = None) -> str:
        ts = time.strftime("%Y%m%d_%H%M%S")
        filename = name or f"api_response_{ts}.txt"
        report_dir = self.config.report_dir if self.config else "./reports"
        path = Path(report_dir) / filename
        path.parent.mkdir(parents=True, exist_ok=True)

        content = str(self._last_response.json() if self._last_response else "No response captured")
        path.write_text(json.dumps(json.loads(content) if isinstance(content, str) else content, indent=2))

        self._screenshots.append(str(path))
        self.logger.info(f"Response saved: {path}")
        return str(path)

    async def get(self, path: str = "", params: Optional[dict] = None,
                  headers: Optional[dict] = None) -> httpx.Response:
        return await self._request("GET", path, params=params, headers=headers)

    async def post(self, path: str = "", json_data: Optional[dict] = None,
                   data: Optional[Any] = None, params: Optional[dict] = None,
                   headers: Optional[dict] = None) -> httpx.Response:
        return await self._request("POST", path, json=json_data, data=data, params=params, headers=headers)

    async def put(self, path: str = "", json_data: Optional[dict] = None,
                  data: Optional[Any] = None, params: Optional[dict] = None,
                  headers: Optional[dict] = None) -> httpx.Response:
        return await self._request("PUT", path, json=json_data, data=data, params=params, headers=headers)

    async def patch(self, path: str = "", json_data: Optional[dict] = None,
                    headers: Optional[dict] = None) -> httpx.Response:
        return await self._request("PATCH", path, json=json_data, headers=headers)

    async def delete(self, path: str = "", params: Optional[dict] = None,
                     headers: Optional[dict] = None) -> httpx.Response:
        return await self._request("DELETE", path, params=params, headers=headers)

    def get_json(self) -> Optional[dict]:
        if self._last_response:
            try:
                return self._last_response.json()
            except Exception:
                pass
        return None

    @property
    def status_code(self) -> Optional[int]:
        return self._last_response.status_code if self._last_response else None

    @property
    def response_headers(self) -> Optional[dict]:
        return dict(self._last_response.headers) if self._last_response else None

    async def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        if not self._client:
            await self.launch()

        url = path if path.startswith("http") else f"{self.base_url}/{path.lstrip('/')}"
        self.logger.info(f"{method} {sanitize_url(url)}")

        response = await self._client.request(method, url, **kwargs)
        self._last_response = response

        status_label = "OK" if 200 <= response.status_code < 300 else f"ERR {response.status_code}"
        self.logger.info(f"  {status_label} ({len(response.content)} bytes)")

        return response

    async def graphql(self, query: str, variables: Optional[dict] = None) -> dict:
        payload = {"query": query}
        if variables:
            payload["variables"] = variables
        resp = await self.post("/graphql", json_data=payload)
        data = resp.json()
        if "errors" in data:
            self.logger.warning(f"GraphQL errors: {data['errors']}")
        return data
