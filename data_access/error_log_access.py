import uuid

from ..errors_db import ErrorsDB


class ErrorLogAccess:

    def insert_and_prune(self, kind: str, title: str, details: str | None, status: int | None, method: str | None,
                         path: str | None, slack_sent: bool, retention_days: int) -> None:
        """Adds one error and, in the same statement, deletes the ones older than retention_days"""
        with ErrorsDB() as db:
            db.void(f"""
                WITH pruned AS (
                    DELETE FROM {db.error_log}
                    WHERE occurred < now() AT TIME ZONE 'UTC' - make_interval(days => @retention_days)
                )
                INSERT INTO {db.error_log} (id, occurred, kind, title, details, status, method, path, slack_sent)
                VALUES (@id, now() AT TIME ZONE 'UTC', @kind, @title, @details, @status, @method, @path, @slack_sent)""",
                    raw_params={"id": str(uuid.uuid4()), "kind": kind, "title": title, "details": details,
                                "status": status, "method": method, "path": path, "slack_sent": slack_sent,
                                "retention_days": int(retention_days)})
