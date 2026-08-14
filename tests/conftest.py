import os

import pytest
from sqlalchemy.orm import sessionmaker

from koshi.db import Base, make_engine
import koshi.models.source_pages  # noqa: F401
import koshi.models.occupations  # noqa: F401
import koshi.models.eoi_rounds  # noqa: F401
import koshi.models.ceiling_usage  # noqa: F401
import koshi.models.occupation_momentum  # noqa: F401

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL", "postgresql+psycopg://koshi:koshi@localhost:5432/koshi_test"
)


@pytest.fixture(scope="session")
def engine():
    eng = make_engine(TEST_DATABASE_URL)
    Base.metadata.create_all(eng)
    yield eng
    Base.metadata.drop_all(eng)
    eng.dispose()


@pytest.fixture()
def db_session(engine):
    Session = sessionmaker(bind=engine, future=True)
    session = Session()
    yield session
    session.rollback()
    for table in reversed(Base.metadata.sorted_tables):
        session.execute(table.delete())
    session.commit()
    session.close()
