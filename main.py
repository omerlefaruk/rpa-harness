#!/usr/bin/env python3
"""Compatibility shim for the packaged rpa-harness CLI."""

from harness.cli import (
    _start_builder_session,
    _telegram_channel_or_skip,
    has_run_failures,
    load_local_env,
    run,
)


if __name__ == "__main__":
    run()
