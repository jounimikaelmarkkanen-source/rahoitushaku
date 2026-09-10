from alembic import context

from funding.db import make_engine
from funding.models import Base
from funding.settings import settings

engine = make_engine(settings())
with engine.connect() as connection:
    context.configure(connection=connection, target_metadata=Base.metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()
