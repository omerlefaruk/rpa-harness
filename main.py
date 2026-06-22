#!/usr/bin/env python3
"""Compatibility shim for the packaged rpa-harness CLI."""

from harness.cli import run


if __name__ == "__main__":
    run()
