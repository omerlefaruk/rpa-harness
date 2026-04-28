"""
Pytest fixtures for RPA Harness.
Provides Playwright driver, Windows UIA driver, API client,
vision engine, RPA Memory recorder, and agent instances.
"""

import pytest
import os


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
def vision_engine(harness_config):
    from harness.ai.vision import VisionEngine

    return VisionEngine(config=harness_config)


@pytest.fixture
def memory_recorder(harness_config):
    from harness.memory import MemoryConfig, MemoryRecorder

    config = MemoryConfig(
        enabled=False,
        worker_url=harness_config.memory.worker_url,
        required=False,
        project=harness_config.memory.project,
    )
    return MemoryRecorder(config=config)


@pytest.fixture
def agent(harness_config, playwright_driver):
    from harness.ai.agent import RPAAgent

    return RPAAgent(
        config=harness_config,
        playwright_driver=playwright_driver,
    )


@pytest.fixture
def excel_handler():
    from harness.rpa.excel import ExcelHandler
    import tempfile

    path = os.path.join(tempfile.gettempdir(), "test_rpa.xlsx")
    excel = ExcelHandler(path)
    yield excel
    excel.close()


@pytest.fixture
def job_queue():
    from harness.rpa.queue import JobQueue

    return JobQueue(max_concurrent=1)
