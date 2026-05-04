# Generated using Claude cli

"""Unit tests for database module"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import CNV_TEST_DB, Base, CnvTestTable, Database  # noqa: E402


class TestCnvTestTable:
    """Test cases for CnvTestTable class"""

    def test_cnv_test_table_structure(self):
        """Test CnvTestTable has expected structure"""
        # Check table name
        assert CnvTestTable.__tablename__ == "CnvTestTable"

        # Check columns exist
        assert hasattr(CnvTestTable, "id")
        assert hasattr(CnvTestTable, "test_name")
        assert hasattr(CnvTestTable, "start_time")

        # Check that it inherits from Base
        assert issubclass(CnvTestTable, Base)


class TestDatabase:
    """Test cases for Database class"""

    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_database_init_with_defaults(self, mock_create_all, mock_get_base, mock_create_engine):
        """Test Database initialization with default parameters"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        db = Database()

        # Check attributes
        assert db.database_file_path == f"/tmp/data/{CNV_TEST_DB}"
        assert db.connection_string == f"sqlite:////tmp/data/{CNV_TEST_DB}"
        assert db.verbose is True
        assert db.engine == mock_engine

        # Check engine creation
        mock_create_engine.assert_called_once_with(
            url=f"sqlite:////tmp/data/{CNV_TEST_DB}",
            echo=True,
        )
        mock_create_all.assert_called_once_with(bind=mock_engine)

    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_database_init_with_custom_params(self, mock_create_all, mock_get_base, mock_create_engine):
        """Test Database initialization with custom parameters"""
        mock_get_base.return_value = "/custom/path/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        db = Database(
            database_file_name="test.db",
            verbose=False,
            base_dir="/custom/dir",
        )

        assert db.database_file_path == "/custom/path/test.db"
        assert db.connection_string == "sqlite:////custom/path/test.db"
        assert db.verbose is False

        mock_get_base.assert_called_once_with(base_dir="/custom/dir")

    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_insert_start_time_new_entry(self, mock_create_all, mock_get_base, mock_create_engine, mock_session_class):
        """Test inserting start time when entry doesn't exist"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock session - no existing entry
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = None
        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        db.insert_start_time(name="test_example", start_time=1234567890)

        # Check that add and commit were called
        mock_session.add.assert_called_once()
        mock_session.commit.assert_called_once()

        # Check the object that was added
        added_obj = mock_session.add.call_args[0][0]
        assert isinstance(added_obj, CnvTestTable)
        assert added_obj.test_name == "test_example"
        assert added_obj.start_time == 1234567890

    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_insert_start_time_already_exists(
        self, mock_create_all, mock_get_base, mock_create_engine, mock_session_class
    ):
        """Test inserting start time when entry already exists (should not insert again)"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock session - existing entry
        existing_entry = MagicMock()
        mock_session = MagicMock()
        mock_session.query.return_value.filter_by.return_value.first.return_value = existing_entry
        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        db.insert_start_time(name="test_example", start_time=1234567890)

        # Check that add and commit were NOT called (entry already exists)
        mock_session.add.assert_not_called()
        mock_session.commit.assert_not_called()

    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_get_start_time_found(self, mock_create_all, mock_get_base, mock_create_engine, mock_session_class):
        """Test getting start time when it exists"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock session and query
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_with_entities = MagicMock()
        mock_filter_by = MagicMock()

        # Setup chain of mocks
        mock_session.query.return_value = mock_query
        mock_query.with_entities.return_value = mock_with_entities
        mock_with_entities.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = [1234567890]

        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        result = db.get_start_time(name="test_example")

        assert result == 1234567890
        mock_session.query.assert_called_once_with(CnvTestTable)
        mock_query.with_entities.assert_called_once_with(CnvTestTable.start_time)
        mock_with_entities.filter_by.assert_called_once_with(test_name="test_example")

    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_database_engine_creation(self, mock_create_all, mock_get_base, mock_create_engine):
        """Test that database engine is created properly"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        db = Database()

        # The engine should be accessible
        assert db.engine is not None
        assert db.engine == mock_engine

    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    def test_get_start_time_not_found(self, mock_create_all, mock_get_base, mock_create_engine, mock_session_class):
        """Test getting start time when it doesn't exist"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock session and query
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_with_entities = MagicMock()
        mock_filter_by = MagicMock()

        # Setup chain of mocks - return None
        mock_session.query.return_value = mock_query
        mock_query.with_entities.return_value = mock_with_entities
        mock_with_entities.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = None

        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        result = db.get_start_time(name="test_example")

        assert result is None

    @patch("database.datetime")
    @patch("database.get_scope_identifier")
    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    @patch("database.LOGGER")
    def test_get_start_time_for_collection_with_module_scope_marker(
        self,
        mock_logger,
        mock_create_all,
        mock_get_base,
        mock_create_engine,
        mock_session_class,
        mock_get_scope_identifier,
        mock_datetime,
    ):
        """Test get_start_time_for_collection with module scope marker"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock node with marker
        mock_node = MagicMock()
        mock_marker = MagicMock()
        mock_marker.kwargs.get.return_value = "module"
        mock_node.get_closest_marker.return_value = mock_marker

        # Mock get_scope_identifier
        mock_get_scope_identifier.return_value = "/path/to/test_module.py"

        # Mock session and query
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_with_entities = MagicMock()
        mock_filter_by = MagicMock()

        mock_session.query.return_value = mock_query
        mock_query.with_entities.return_value = mock_with_entities
        mock_with_entities.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = [1234567890]

        mock_session_class.return_value.__enter__.return_value = mock_session

        # Mock datetime for time delta calculation
        mock_datetime_now = MagicMock()
        mock_datetime_now.strftime.return_value = "1234567990"
        mock_datetime.datetime.now.return_value = mock_datetime_now

        db = Database()
        result = db.get_start_time_for_collection(node=mock_node)

        assert result == 1234567890
        mock_node.get_closest_marker.assert_called_once_with(name="data_collector_scope")
        mock_marker.kwargs.get.assert_called_once_with("scope")
        mock_get_scope_identifier.assert_called_once_with(node=mock_node, scope_value="module")
        mock_logger.info.assert_called_once()
        assert "MODULE scope: 100s (1m)" in mock_logger.info.call_args[0][0]

    @patch("database.datetime")
    @patch("database.get_scope_identifier")
    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    @patch("database.LOGGER")
    def test_get_start_time_for_collection_with_class_scope_marker(
        self,
        mock_logger,
        mock_create_all,
        mock_get_base,
        mock_create_engine,
        mock_session_class,
        mock_get_scope_identifier,
        mock_datetime,
    ):
        """Test get_start_time_for_collection with class scope marker"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock node with marker
        mock_node = MagicMock()
        mock_marker = MagicMock()
        mock_marker.kwargs.get.return_value = "class"
        mock_node.get_closest_marker.return_value = mock_marker

        # Mock get_scope_identifier
        mock_get_scope_identifier.return_value = "/path/to/test_file.py::TestClass"

        # Mock session and query
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_with_entities = MagicMock()
        mock_filter_by = MagicMock()

        mock_session.query.return_value = mock_query
        mock_query.with_entities.return_value = mock_with_entities
        mock_with_entities.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = [1700000000]

        mock_session_class.return_value.__enter__.return_value = mock_session

        # Mock datetime for time delta calculation
        mock_datetime_now = MagicMock()
        mock_datetime_now.strftime.return_value = "1700000120"
        mock_datetime.datetime.now.return_value = mock_datetime_now

        db = Database()
        result = db.get_start_time_for_collection(node=mock_node)

        assert result == 1700000000
        mock_get_scope_identifier.assert_called_once_with(node=mock_node, scope_value="class")
        mock_logger.info.assert_called_once()
        assert "CLASS scope: 120s (2m)" in mock_logger.info.call_args[0][0]

    @patch("database.datetime")
    @patch("database.get_scope_identifier")
    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    @patch("database.LOGGER")
    def test_get_start_time_for_collection_without_marker(
        self,
        mock_logger,
        mock_create_all,
        mock_get_base,
        mock_create_engine,
        mock_session_class,
        mock_get_scope_identifier,
        mock_datetime,
    ):
        """Test get_start_time_for_collection without marker (test scope)"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock node without marker
        mock_node = MagicMock()
        mock_node.get_closest_marker.return_value = None

        # Mock get_scope_identifier
        mock_get_scope_identifier.return_value = "/path/to/test_file.py::test_function"

        # Mock session and query
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_with_entities = MagicMock()
        mock_filter_by = MagicMock()

        mock_session.query.return_value = mock_query
        mock_query.with_entities.return_value = mock_with_entities
        mock_with_entities.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = [1600000000]

        mock_session_class.return_value.__enter__.return_value = mock_session

        # Mock datetime for time delta calculation
        mock_datetime_now = MagicMock()
        mock_datetime_now.strftime.return_value = "1600000300"
        mock_datetime.datetime.now.return_value = mock_datetime_now

        db = Database()
        result = db.get_start_time_for_collection(node=mock_node)

        assert result == 1600000000
        mock_get_scope_identifier.assert_called_once_with(node=mock_node, scope_value=None)
        mock_logger.info.assert_called_once()
        assert "TEST scope: 300s (5m)" in mock_logger.info.call_args[0][0]

    @patch("database.get_scope_identifier")
    @patch("database.Session")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    @patch("database.LOGGER")
    def test_get_start_time_for_collection_not_found(
        self,
        mock_logger,
        mock_create_all,
        mock_get_base,
        mock_create_engine,
        mock_session_class,
        mock_get_scope_identifier,
    ):
        """Test get_start_time_for_collection when start time not found in database"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock node
        mock_node = MagicMock()
        mock_node.get_closest_marker.return_value = None

        # Mock get_scope_identifier
        mock_get_scope_identifier.return_value = "/path/to/test_file.py::test_function"

        # Mock session and query - return None (not found)
        mock_session = MagicMock()
        mock_query = MagicMock()
        mock_with_entities = MagicMock()
        mock_filter_by = MagicMock()

        mock_session.query.return_value = mock_query
        mock_query.with_entities.return_value = mock_with_entities
        mock_with_entities.filter_by.return_value = mock_filter_by
        mock_filter_by.first.return_value = None

        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        result = db.get_start_time_for_collection(node=mock_node)

        assert result == 0
        mock_logger.warning.assert_called_once()
        assert "Start time not found" in mock_logger.warning.call_args[0][0]

    @patch("database.get_scope_identifier")
    @patch("database.create_engine")
    @patch("database.get_data_collector_base")
    @patch("database.Base.metadata.create_all")
    @patch("database.LOGGER")
    def test_get_start_time_for_collection_exception_handling(
        self, mock_logger, mock_create_all, mock_get_base, mock_create_engine, mock_get_scope_identifier
    ):
        """Test get_start_time_for_collection handles exceptions gracefully"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock node that raises exception
        mock_node = MagicMock()
        mock_node.get_closest_marker.side_effect = Exception("Database connection error")

        db = Database()
        result = db.get_start_time_for_collection(node=mock_node)

        assert result == 0
        mock_logger.warning.assert_called_once()
        assert "Error:" in mock_logger.warning.call_args[0][0]
        assert "Database connection error" in mock_logger.warning.call_args[0][0]
