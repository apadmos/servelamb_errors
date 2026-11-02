from ..errors_db import ErrorsDB


class ErrorThrottleAccess:

    def claim(self, kind: str, throttle_seconds: float):
        """
        One statement, so Lambda containers reporting at the same time agree on who sends.
        Outside the throttle window: last_sent becomes now, held_back resets, should_send is true.
        Inside it: held_back goes up by one, should_send is false.
        held_back_before is the count from before this call, for the message that's sent. previous has no FOR UPDATE:
        it's only read in RETURNING, after this statement has updated the row, and FOR UPDATE would then skip it.
        ON CONFLICT already locks the row, so a second container waits and then sees the new last_sent.
        Returns a row with should_send and held_back_before.
        """
        with ErrorsDB() as db:
            return db.read_first(f"""
                WITH previous AS (
                    SELECT held_back FROM {db.error_throttle} WHERE kind = @kind
                )
                INSERT INTO {db.error_throttle} AS throttle (kind, last_sent, held_back)
                VALUES (@kind, now() AT TIME ZONE 'UTC', 0)
                ON CONFLICT (kind) DO UPDATE SET
                    held_back = CASE
                        WHEN throttle.last_sent > now() AT TIME ZONE 'UTC' - make_interval(secs => @throttle_seconds)
                        THEN throttle.held_back + 1 ELSE 0 END,
                    last_sent = CASE
                        WHEN throttle.last_sent > now() AT TIME ZONE 'UTC' - make_interval(secs => @throttle_seconds)
                        THEN throttle.last_sent ELSE now() AT TIME ZONE 'UTC' END
                RETURNING throttle.last_sent = now() AT TIME ZONE 'UTC' AS should_send,
                    COALESCE((SELECT held_back FROM previous), 0) AS held_back_before""",
                                raw_params={"kind": kind, "throttle_seconds": float(throttle_seconds)},
                                commit=True)
