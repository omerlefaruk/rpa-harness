"""Pytest fixtures for RPA Harness drivers and helpers."""

from __future__ import annotations

import os

import pytest


@pytest.fixture
def harness_config():
    from harness.config import HarnessConfig

    return HarnessConfig.from_env()


@pytest.fixture
async def playwright_driver(harness_config):
    from harness.drivers.playwright import PlaywrightDriver

    driver = await PlaywrightDriver.launch(config=harness_config)
    yield driver
    await driver.close()


@pytest.fixture
def windows_driver(harness_config):
    from harness.drivers.windows_ui import WindowsUIDriver

    driver = WindowsUIDriver(config=harness_config)
    yield driver
    import asyncio

    asyncio.get_event_loop().run_until_complete(driver.close())


@pytest.fixture
async def api_driver(harness_config):
    from harness.drivers.api import APIDriver

    driver = APIDriver(config=harness_config)
    await driver.launch()
    yield driver
    await driver.close()


@pytest.fixture
def excel_handler():
    import tempfile

    from harness.rpa.excel import ExcelHandler

    path = os.path.join(tempfile.gettempdir(), "test_rpa.xlsx")
    excel = ExcelHandler(path)
    yield excel
    excel.close()
