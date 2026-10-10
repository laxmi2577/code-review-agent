import json
import logging

from src.utils.logging import JSONFormatter, request_id_ctx, setup_logging


def test_json_formatter_basic():
    formatter = JSONFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test message with %s",
        args=("arg1",),
        exc_info=None,
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert data["level"] == "INFO"
    assert data["logger"] == "test_logger"
    assert data["message"] == "Test message with arg1"
    assert "timestamp" in data


def test_json_formatter_with_request_id():
    formatter = JSONFormatter()
    token = request_id_ctx.set("req-uuid-1234")
    try:
        record = logging.LogRecord(
            name="test_logger",
            level=logging.WARNING,
            pathname="test.py",
            lineno=20,
            msg="Warning message",
            args=(),
            exc_info=None,
        )
        output = formatter.format(record)
        data = json.loads(output)
        assert data["request_id"] == "req-uuid-1234"
    finally:
        request_id_ctx.reset(token)


def test_json_formatter_with_exception():
    formatter = JSONFormatter()
    try:
        raise ValueError("Simulated failure")
    except ValueError:
        import sys

        exc_info = sys.exc_info()

    record = logging.LogRecord(
        name="test_logger",
        level=logging.ERROR,
        pathname="test.py",
        lineno=30,
        msg="Error occurred",
        args=(),
        exc_info=exc_info,
    )
    output = formatter.format(record)
    data = json.loads(output)

    assert "exception" in data
    assert "Simulated failure" in data["exception"]


def test_setup_logging():
    setup_logging(log_level="DEBUG")
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JSONFormatter)
