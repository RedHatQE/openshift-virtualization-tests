"""Unit tests for database module"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add utilities to Python path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from database import CNV_TEST_DB, Base, CnvTestTable, Database


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
    def test_insert_test_start_time(self, mock_create_all, mock_get_base, mock_create_engine, mock_session_class):
        """Test inserting test start time"""
        mock_get_base.return_value = "/tmp/data/"
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine

        # Mock session
        mock_session = MagicMock()
        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        db.insert_test_start_time("test_example", 1234567890)

        # Check Session was created with the engine
        mock_session_class.assert_called_once_with(bind=mock_engine)

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
    def test_get_test_start_time(self, mock_create_all, mock_get_base, mock_create_engine, mock_session_class):
        """Test getting test start time"""
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
        mock_filter_by.one.return_value = [1234567890]

        mock_session_class.return_value.__enter__.return_value = mock_session

        db = Database()
        result = db.get_test_start_time("test_example")

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
