import datetime
import logging

from _pytest.nodes import Collector
from pytest import Item
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from utilities.data_collector import get_data_collector_base, get_scope_identifier

LOGGER = logging.getLogger(__name__)

CNV_TEST_DB = "cnvtests.db"


class Base(DeclarativeBase):
    pass


class CnvTestTable(Base):
    __tablename__ = "CnvTestTable"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, nullable=False)
    test_name: Mapped[str] = mapped_column(String(500))
    start_time: Mapped[int] = mapped_column(Integer, nullable=False)


class Database:
    def __init__(
        self, database_file_name: str = CNV_TEST_DB, verbose: bool = True, base_dir: str | None = None
    ) -> None:
        self.database_file_path = f"{get_data_collector_base(base_dir=base_dir)}{database_file_name}"
        self.connection_string = f"sqlite:///{self.database_file_path}"
        self.verbose = verbose
        self.engine = create_engine(url=self.connection_string, echo=self.verbose)
        Base.metadata.create_all(bind=self.engine)

    def insert_start_time(self, name: str, start_time: int) -> None:
        """
        Insert start time only if it doesn't exist.

        Args:
            name (str): Test/class/module identifier.
            start_time (int): Start time in seconds since epoch.
        """
        with Session(bind=self.engine) as db_session:
            existing_entry = db_session.query(CnvTestTable).filter_by(test_name=name).first()

            if not existing_entry:
                new_entry = CnvTestTable(test_name=name, start_time=start_time)
                db_session.add(new_entry)
                db_session.commit()

    def get_start_time(self, name: str) -> int | None:
        """
        Get the start time for a test/class/module.

        Args:
            name (str): Test/class/module identifier.

        Returns:
            int | None: Start time in seconds since epoch, or None if not found.
        """
        with Session(bind=self.engine) as db_session:
            result = (
                db_session.query(CnvTestTable).with_entities(CnvTestTable.start_time).filter_by(test_name=name).first()
            )
            return result[0] if result else None

    def get_start_time_for_collection(self, node: Item | Collector) -> int:
        """
        Get test start time based on data_collector_scope marker.

        Determines the appropriate scope (test, class, or module) from the marker,
        retrieves the start time from the database, and logs the time delta.

        Args:
            node: Pytest node (Item or Collector).

        Returns:
            Start time in seconds since epoch, or 0 if not found.
        """
        try:
            # Check data_collector_scope marker
            scope_marker = node.get_closest_marker(name="data_collector_scope")
            scope_value = scope_marker.kwargs.get("scope") if scope_marker else None

            name = get_scope_identifier(node=node, scope_value=scope_value)
            scope_label = scope_value.upper() if scope_value else "TEST"

            test_start_time = self.get_start_time(name=name)
            if test_start_time:
                time_delta = int(datetime.datetime.now().strftime("%s")) - test_start_time
                LOGGER.info(f"[DATA_COLLECTOR] {scope_label} scope: {time_delta}s ({time_delta // 60}m)")
            else:
                test_start_time = 0
                LOGGER.warning(f"[DATA_COLLECTOR] Start time not found for {name}")
        except Exception as db_exception:
            test_start_time = 0
            LOGGER.warning(f"[DATA_COLLECTOR] Error: {db_exception} in accessing database.")

        return test_start_time
