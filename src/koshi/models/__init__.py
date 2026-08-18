"""Importing this package registers every model on koshi.db.Base.metadata.

A single `import koshi.models` (rather than each caller enumerating every
model module by hand) is what guarantees Base.metadata is fully populated —
for Alembic autogenerate/migrations and for the test suite's
Base.metadata.create_all()/drop_all(). Add new model modules here as they're
added under koshi/models/.
"""

from koshi.models import (  # noqa: F401
    ceiling_usage,
    eoi_rounds,
    occupation_momentum,
    occupation_titles,
    occupations,
    source_pages,
)
