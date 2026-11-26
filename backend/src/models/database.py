from redis import Redis
from sqlalchemy import create_engine, insert, inspect, select, text

from src.config.settings import DATABASE_URL, REDIS_URL
from src.models.tables import audit, metadata, runs

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
cache = Redis.from_url(REDIS_URL, socket_connect_timeout=2, socket_timeout=2)


def ensure_schema():
    metadata.create_all(engine)
    with engine.begin() as connection:
        columns = {column['name'] for column in inspect(connection).get_columns(runs.name)}
        if 'thresholds' not in columns:
            connection.execute(text('ALTER TABLE analysis_runs ADD COLUMN thresholds JSON'))


def fetch_one(connection, table, key):
    return connection.execute(select(table).where(table.c.id == key)).mappings().one_or_none()


def add_event(connection, actor, action, subject, at):
    connection.execute(insert(audit).values(actor=actor, action=action, subject=subject, at=at))
