import uuid

from ..errors_db import ErrorsDB


class ErrorLogAccess:

    def insert_and_prune(self, kind: str, title: str, details: str | None, status: int | None, method: str | None,
                         path: str | None, slack_sent: bool, max_rows: int) -> None:
        """Adds one error and, in the same statement, deletes all but the newest max_rows.
        The DELETE sees the table from before this INSERT, so it keeps max_rows - 1 to leave room for the new row"""
        with ErrorsDB() as db:
            db.void(f"""
                WITH pruned AS (
                    DELETE FROM {db.error_log}
                    WHERE id IN (SELECT id FROM {db.error_log} ORDER BY occurred DESC OFFSET @keep_existing)
                )
                INSERT INTO {db.error_log} (id, occurred, kind, title, details, status, method, path, slack_sent)
                VALUES (@id, now() AT TIME ZONE 'UTC', @kind, @title, @details, @status, @method, @path, @slack_sent)""",
                    raw_params={"id": str(uuid.uuid4()), "kind": kind, "title": title, "details": details,
                                "status": status, "method": method, "path": path, "slack_sent": slack_sent,
                                "keep_existing": max(int(max_rows) - 1, 0)})
