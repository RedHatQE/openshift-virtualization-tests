# Generated using Claude cli

"""Unit tests for logger.py - independent of main project tests"""

import logging
from unittest.mock import MagicMock, Mock, patch

from logger import (
    DuplicateFilter,
    TestLogFormatter,
    setup_logging,
)


class TestDuplicateFilter:
    """Test cases for DuplicateFilter class"""

    def test_filter_first_message(self):
        """Test that first message is allowed through"""
        log_filter = DuplicateFilter()
        record = Mock()
        record.module = "test_module"
        record.levelno = logging.INFO
        record.msg = "Test message"

        result = log_filter.filter(record)

        assert result is True
        assert log_filter.last_log == ("test_module", logging.INFO, "Test message")
        assert log_filter.repeated_number == 0

    def test_filter_duplicate_message(self):
        """Test that duplicate messages are filtered"""
        log_filter = DuplicateFilter()
        record = Mock()
        record.module = "test_module"
        record.levelno = logging.INFO
        record.msg = "Test message"

        # First message
        log_filter.filter(record)
        # Duplicate message
        result = log_filter.filter(record)

        assert result is False
        assert log_filter.repeated_number == 1

    def test_filter_multiple_duplicates(self):
        """Test counting of multiple duplicate messages"""
        log_filter = DuplicateFilter()
        record = Mock()
        record.module = "test_module"
        record.levelno = logging.INFO
        record.msg = "Test message"

        # First message
        log_filter.filter(record)
        # Multiple duplicates
        for _ in range(5):
            log_filter.filter(record)

        assert log_filter.repeated_number == 5

    @patch("logger.LOGGER")
    def test_filter_new_message_after_duplicates(self, mock_logger):
        """Test that new message after duplicates logs the repeat count"""
        log_filter = DuplicateFilter()
        record1 = Mock()
        record1.module = "test_module"
        record1.levelno = logging.INFO
        record1.msg = "Test message 1"

        record2 = Mock()
        record2.module = "test_module"
        record2.levelno = logging.INFO
        record2.msg = "Test message 2"

        # First message
        log_filter.filter(record1)
        # Duplicate
        log_filter.filter(record1)
        # New message
        result = log_filter.filter(record2)

        assert result is True
        mock_logger.warning.assert_called_once_with("Last log repeated 1 times.")


def test_log_formatter_time_format():
    """Test TestLogFormatter formats time correctly"""
    formatter = TestLogFormatter()

    # Create a log record
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Test message",
        args=(),
        exc_info=None,
    )

    # The formatter should format time as a delta
    formatted_time = formatter.formatTime(record)
    # Should be a string representing time delta
    assert isinstance(formatted_time, str)
    assert ":" in formatted_time  # Should contain time separator


class TestSetupLogging:
    """Test cases for setup_logging function"""

    @patch("logger.multiprocessing.Queue")
    @patch("logger.QueueListener")
    @patch("logger.logging.StreamHandler")
    @patch("logger.RotatingFileHandler")
    def test_setup_logging_default_log_file(
        self,
        mock_file_handler,
        mock_stream_handler,
        mock_queue_listener,
        mock_queue,
    ):
        """Test setup_logging with default log file"""
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_listener_instance = MagicMock()
        mock_queue_listener.return_value = mock_listener_instance

        result = setup_logging(logging.INFO)

        # Verify default log file is used
        mock_file_handler.assert_called_once_with(
            filename="/tmp/pytest-tests.log",
            maxBytes=100 * 1024 * 1024,
            backupCount=20,
        )

        # Verify queue listener is started
        mock_listener_instance.start.assert_called_once()

        # Verify the returned listener
        assert result == mock_listener_instance

    @patch("logger.multiprocessing.Queue")
    @patch("logger.QueueListener")
    @patch("logger.logging.StreamHandler")
    @patch("logger.RotatingFileHandler")
    def test_setup_logging_custom_log_file(
        self,
        mock_file_handler,
        mock_stream_handler,
        mock_queue_listener,
        mock_queue,
    ):
        """Test setup_logging with custom log file"""
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance
        mock_listener_instance = MagicMock()
        mock_queue_listener.return_value = mock_listener_instance
        custom_log_file = "/custom/path/test.log"

        result = setup_logging(logging.DEBUG, custom_log_file)

        # Verify custom log file is used
        mock_file_handler.assert_called_once_with(
            filename=custom_log_file,
            maxBytes=100 * 1024 * 1024,
            backupCount=20,
        )

        # Verify the returned listener
        assert result == mock_listener_instance

    @patch("logger.logging.getLogger")
    def test_setup_logging_configures_loggers(self, mock_get_logger):
        """Test that setup_logging properly configures basic and root loggers"""
        mock_basic_logger = MagicMock()
        mock_root_logger = MagicMock()
        mock_get_logger.side_effect = lambda name="": (mock_basic_logger if name == "basic" else mock_root_logger)

        with (
            patch("logger.multiprocessing.Queue"),
            patch("logger.QueueListener") as mock_listener,
            patch(
                "logger.logging.StreamHandler",
            ),
            patch("logger.RotatingFileHandler"),
        ):
            mock_listener_instance = MagicMock()
            mock_listener.return_value = mock_listener_instance

            setup_logging(logging.WARNING)

        # Verify basic logger configuration
        mock_basic_logger.setLevel.assert_called_once_with(level=logging.WARNING)
        mock_basic_logger.addHandler.assert_called_once()
        assert mock_basic_logger.propagate is False

        # Verify root logger configuration
        mock_root_logger.setLevel.assert_called_once_with(level=logging.WARNING)
        mock_root_logger.addHandler.assert_called_once()
        mock_root_logger.addFilter.assert_called_once()
        assert mock_root_logger.propagate is False

    @patch("logger.QueueHandler")
    @patch("logger.multiprocessing.Queue")
    @patch("logger.QueueListener")
    @patch("logger.logging.StreamHandler")
    @patch("logger.RotatingFileHandler")
    def test_setup_logging_queue_configuration(
        self,
        mock_file_handler,
        mock_stream_handler,
        mock_queue_listener,
        mock_queue,
        mock_queue_handler,
    ):
        """Test that queue is properly configured"""
        mock_queue_instance = MagicMock()
        mock_queue.return_value = mock_queue_instance

        setup_logging(logging.INFO)

        # Verify queue is created with no size limit
        mock_queue.assert_called_once_with(maxsize=-1)

        # Verify QueueListener is created with correct handlers
        mock_queue_listener.assert_called_once_with(
            mock_queue_instance,
            mock_file_handler.return_value,
            mock_stream_handler.return_value,
        )

        # Verify QueueHandler is created with the queue
        assert mock_queue_handler.call_count == 2  # One for basic, one for root
        mock_queue_handler.assert_any_call(queue=mock_queue_instance)
