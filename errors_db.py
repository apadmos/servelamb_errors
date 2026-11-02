from subs.crudepg.db_base import PostgresDB
from subs.crudepg.db_table_definition import DbColumnDefinition as C
from subs.crudepg.db_table_definition import DbTableDefinition
"""Absolute, like servelamb_users.users_db, so this file can also be run directly to create its tables"""
from servelamb_errors.errors_config import ErrorsConfig


class ErrorsDB(PostgresDB):
    """The database named in servelamb_errors.yaml. Its table can share a schema with the app's tables"""

    def __init__(self):
        settings = ErrorsConfig.settings().database
        if not settings:
            raise Exception(f"No database in {ErrorsConfig.config_file_name}")
        super().__init__(
            host=settings.host,
            user=settings.user,
            password=settings.password,
            database=settings.database,
            port=settings.port
        )
        self.schema = settings.schema

        """One row per kind of error ("exception", "404", "startup"...): when its last message was sent
        and how many were held back by the throttle since"""
        self.error_throttle = self.register_table(DbTableDefinition(
            schema=self.schema,
            name='error_throttle',
            column_definitions=[
                C(name="kind", data_type="varchar", length=50, is_primary_key=True, nullable=False),
                C(name="last_sent", data_type="timestamp", nullable=False),
                C(name="held_back", data_type="int", nullable=False),
            ],
        ))

        """Every error reported, sent to Slack or not, for showing in an app and for a daily summary.
        Only the newest log_max_rows are kept: the oldest are deleted each time one is added"""
        self.error_log = self.register_table(DbTableDefinition(
            schema=self.schema,
            name='error_log',
            column_definitions=[
                C(name="id", data_type="varchar", length=50, is_primary_key=True, nullable=False),
                C(name="occurred", data_type="timestamp", nullable=False),  # UTC
                C(name="kind", data_type="varchar", length=50, nullable=False),
                C(name="title", data_type="text", nullable=False),
                C(name="details", data_type="text", nullable=True),
                # set for error responses; exceptions carry their request in the title
                C(name="status", data_type="int", nullable=True),
                C(name="method", data_type="varchar", length=10, nullable=True),
                C(name="path", data_type="text", nullable=True),
                # false when the throttle held it back, Slack is off, or sending failed
                C(name="slack_sent", data_type="boolean", nullable=False),
                # when a daily summary included it (UTC); NULL until then. Not used yet
                C(name="digest_sent", data_type="timestamp", nullable=True),
            ],
        ))


if __name__ == '__main__':
    """Creates or updates this module's tables only. Not cli_main: its "recreate" drops the whole schema,
    which is shared with the app"""
    with ErrorsDB() as db:
        db.resolve_table_differences(db.error_throttle)
        db.resolve_table_differences(db.error_log)
