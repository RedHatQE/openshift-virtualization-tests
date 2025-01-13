import logging
import multiprocessing
from datetime import datetime
from logging.handlers import QueueHandler, QueueListener, RotatingFileHandler

from colorlog import ColoredFormatter

LOGGER = logging.getLogger(__name__)


class DuplicateFilter(logging.Filter):
    def filter(self, record):
        repeated_number_exists = getattr(self, "repeated_number", None)
        current_log = (record.module, record.levelno, record.msg)
        if current_log != getattr(self, "last_log", None):
            self.last_log = current_log
            if repeated_number_exists:
                LOGGER.warning(f"Last log repeated {self.repeated_number} times.")

            self.repeated_number = 0
            return True
        if repeated_number_exists:
            self.repeated_number += 1
        else:
            self.repeated_number = 1
        return False


class TestLogFormatter(ColoredFormatter):
    def formatTime(self, record, datefmt=None):  # noqa: N802
        return datetime.fromtimestamp(record.created).isoformat()


def setup_logging(log_level, log_file="/tmp/pytest-tests.log"):
    """
    Setup basic/root logging using QueueHandler/QueueListener
    to consolidate log messages into a single stream to be written to multiple outputs.

    Args:
        log_level (int): log level
        log_file (str): logging output file

    Returns:
        QueueListener: Process monitoring the log Queue

    Eg:
       root QueueHandler ┐                         ┌> StreamHandler
                         ├> Queue -> QueueListener ┤
      basic QueueHandler ┘                         └> FileHandler
    """
    basic_log_formatter = logging.Formatter(fmt="%(message)s")
    root_log_formatter = TestLogFormatter(
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
    log_file_handler = RotatingFileHandler(filename=log_file, maxBytes=100 * 1024 * 1024, backupCount=20)

    log_queue = multiprocessing.Queue(maxsize=-1)
    log_listener = QueueListener(
        log_queue,
        log_file_handler,
        console_handler,
    )

    basic_log_queue_handler = QueueHandler(queue=log_queue)
    basic_log_queue_handler.set_name(name="basic")
    basic_log_queue_handler.setFormatter(fmt=basic_log_formatter)

    basic_logger = logging.getLogger("basic")
    basic_logger.setLevel(level=log_level)
    basic_logger.addHandler(hdlr=basic_log_queue_handler)

    root_log_queue_handler = QueueHandler(queue=log_queue)
    root_log_queue_handler.set_name(name="root")
    root_log_queue_handler.setFormatter(fmt=root_log_formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level=log_level)
    root_logger.addHandler(hdlr=root_log_queue_handler)
    root_logger.addFilter(filter=DuplicateFilter())

    root_logger.propagate = False
    basic_logger.propagate = False

    log_listener.start()
    return log_listener
