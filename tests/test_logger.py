"""Tests for harness logging."""

import io
import logging

from harness.logger import SafeStreamHandler


class Cp1252Stream(io.StringIO):
    encoding = "cp1252"

    def write(self, value):
        value.encode(self.encoding)
        return super().write(value)


def test_safe_stream_handler_escapes_unencodable_stdout_text():
    logger = logging.getLogger("tests.safe-stream-handler")
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(logging.INFO)
    stream = Cp1252Stream()
    handler = SafeStreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)

    logger.info("Navigate \u2192 target")

    assert "Navigate \\u2192 target" in stream.getvalue()