import logging

from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from utilities.data_collector import get_data_collector_base

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
    def __init__(self, database_file_name: str = CNV_TEST_DB, verbose: bool = True) -> None:
        self.database_file_path = f"{get_data_collector_base()}{database_file_name}"
        self.connection_string = f"sqlite:///{self.database_file_path}"
        self.verbose = verbose
        self.engine = create_engine(url=self.connection_string, echo=self.verbose)
        Base.metadata.create_all(bind=self.engine)

    def insert_test_start_time(self, test_name: str, start_time: int) -> None:
        with Session(bind=self.engine) as db_session:
            new_table_entry = CnvTestTable(test_name=test_name, start_time=start_time)
            db_session.add(new_table_entry)
            db_session.commit()

    def get_test_start_time(self, test_name: str) -> int:
        with Session(bind=self.engine) as db_session:
            return (
                db_session.query(CnvTestTable)
                .with_entities(CnvTestTable.start_time)
                .filter_by(test_name=test_name)
                .one()[0]
            )
