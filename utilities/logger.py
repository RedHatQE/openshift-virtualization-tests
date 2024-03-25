import logging
from datetime import datetime
from logging.handlers import RotatingFileHandler
from simple_logger.logger import DuplicateFilter
from colorlog import ColoredFormatter


LOGGER = logging.getLogger(__name__)


class TestLogFormatter(ColoredFormatter):
    def formatTime(self, record, datefmt=None):  # noqa: N802
        return datetime.fromtimestamp(record.created).isoformat()


def setup_logging(log_level, log_file="/tmp/pytest-tests.log"):
    logger_obj = logging.getLogger()
    basic_logger = logging.getLogger("basic")

    root_log_formatter = logging.Formatter(fmt="%(message)s")
    log_formatter = TestLogFormatter(
        fmt="%(asctime)s %(name)s %(log_color)s%(levelname)s%(reset)s %(message)s",
        log_colors={
            "DEBUG": "cyan",
            "INFO": "green",
            "WARNING": "yellow",
            "ERROR": "red",
            "CRITICAL": "red,bg_white",
        },
        secondary_log_colors={},
    )

    console_handler = logging.StreamHandler()
    log_handler = RotatingFileHandler(
        filename=log_file, maxBytes=100 * 1024 * 1024, backupCount=20
    )
    basic_console_handler = logging.StreamHandler()
    basic_log_handler = RotatingFileHandler(
        filename=log_file, maxBytes=100 * 1024 * 1024, backupCount=20
    )

    basic_log_handler.setFormatter(fmt=root_log_formatter)
    basic_console_handler.setFormatter(fmt=root_log_formatter)
    basic_logger.addHandler(hdlr=basic_log_handler)
    basic_logger.addHandler(hdlr=basic_console_handler)
    basic_logger.setLevel(level=log_level)

    log_handler.setFormatter(fmt=log_formatter)
    console_handler.setFormatter(fmt=log_formatter)

    logger_obj.addHandler(hdlr=console_handler)
    logger_obj.addHandler(hdlr=log_handler)
    logger_obj.setLevel(level=log_level)

    logger_obj.addFilter(filter=DuplicateFilter())
    console_handler.addFilter(filter=DuplicateFilter())

    logger_obj.propagate = False
    basic_logger.propagate = False
