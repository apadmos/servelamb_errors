import json
import traceback
import urllib.request

from .errors_config import ErrorsConfig, ErrorReportingSettings


class ErrorReporter:
    """
    Sends an app's own errors to Slack, with settings from servelamb_errors.yaml (see ErrorsConfig).

    The throttle (one message per kind of error per throttle_minutes) is kept in the error_throttle table, because
    on Lambda nothing in memory outlives a request. When that table can't be read, every error is sent.
    Urgent reports skip the throttle.
    Every error, sent or held back, is also added to error_log, which keeps the last log_retention_days.

    It never raises. If reporting itself fails, one plain message about that failure is attempted straight to the
    webhook, skipping the throttle and the formatting.
    """
    SLACK_TIMEOUT_SECONDS: float = 3
    MAX_DETAIL_CHARS: int = 2500

    @classmethod
    def report(cls, kind: str, title: str, details: str | None = None, urgent: bool = False,
               status: int | None = None, method: str | None = None, path: str | None = None) -> None:
        """kind groups errors for the throttle ("exception", "404", "startup"); title is the first line in Slack.
        status, method and path are only stored in the log"""
        settings: ErrorReportingSettings | None = None
        slack_sent: bool = False
        try:
            settings = ErrorsConfig.settings()
            if settings.slack_webhook_url:
                slack_sent = cls._send(settings=settings, kind=kind, title=title, details=details, urgent=urgent)
        except Exception as reporting_error:
            cls._report_own_failure(settings=settings, title=title, details=details, reporting_error=reporting_error)
        """Logged after sending, so slack_sent is known. A log failure is printed and doesn't affect Slack"""
        if settings and settings.database:
            try:
                from .data_access.error_log_access import ErrorLogAccess
                ErrorLogAccess().insert_and_prune(kind=kind, title=title, details=details, status=status,
                                                  method=method, path=path, slack_sent=slack_sent,
                                                  retention_days=settings.log_retention_days)
            except Exception as log_error:
                print(f"servelamb_errors: could not log the error: {log_error!r}")

    @classmethod
    def _send(cls, settings: ErrorReportingSettings, kind: str, title: str, details: str | None,
              urgent: bool) -> bool:
        """Sends to Slack unless the throttle holds it back. True when it was sent"""
        throttle_note: str = ""
        if settings.throttle_minutes and not urgent:
            should_send, held_back, throttle_note = cls._check_throttle(settings=settings, kind=kind)
            if not should_send:
                return False
            if held_back:
                throttle_note = (f"\n_{held_back} more \"{kind}\" errors were held back by the "
                                 f"{settings.throttle_minutes:g} minute throttle_")

        mention: str = f"{settings.slack_mention} " if settings.slack_mention else ""
        detail_block: str = f"\n```{details[:cls.MAX_DETAIL_CHARS]}```" if details else ""
        text: str = f"{mention}*[{settings.environment_label}] {title}*{detail_block}{throttle_note}"
        cls._post(url=settings.slack_webhook_url, text=text)
        return True

    @classmethod
    def _check_throttle(cls, settings: ErrorReportingSettings, kind: str) -> tuple[bool, int, str]:
        """(should send, how many were held back before this one, a note when the throttle couldn't be read).
        No database, or one that can't be reached: send everything"""
        if not settings.database:
            return True, 0, ""
        try:
            from .data_access.error_throttle_access import ErrorThrottleAccess
            claimed = ErrorThrottleAccess().claim(kind=kind, throttle_seconds=settings.throttle_minutes * 60)
            return bool(claimed.should_send), int(claimed.held_back_before or 0), ""
        except Exception as throttle_error:
            print(f"servelamb_errors: throttle state unavailable, sending: {throttle_error!r}")
            return True, 0, f"\n_Throttle state unavailable, so every error is being sent: {throttle_error!r}_"

    @classmethod
    def report_response(cls, req, resp) -> None:
        """For a ServerApp before_response hook: reports the response if its status matches report_status_codes.
        An exception in a controller leaves the status at 200, so it's reported once, as an exception, not here"""
        settings: ErrorReportingSettings | None = None
        try:
            settings = ErrorsConfig.settings()
            if not settings.slack_webhook_url and not settings.database:
                return
            if not cls.status_matches(status=resp.status, patterns=settings.report_status_codes):
                return
            headers: dict = req.headers or {}
            details: str = "\n".join([
                f"Referer: {headers.get('referer') or '(none)'}",
                f"User agent: {headers.get('user-agent') or '(none)'}",
                f"Response: {str(resp.body or '')[:500]}",
            ])
            cls.report(kind=str(resp.status), title=f"{resp.status} {req.method} {req.path}", details=details,
                       status=resp.status, method=req.method, path=req.path)
        except Exception as reporting_error:
            cls._report_own_failure(settings=settings, title=f"{resp.status} response", details=None,
                                    reporting_error=reporting_error)

    @staticmethod
    def status_matches(status: int, patterns: list[str]) -> bool:
        """True when the status fits one of the patterns: "404" exactly, or "5xx" / "5**" for any 5 hundred"""
        status_text: str = str(status)
        for pattern in patterns:
            pattern_text: str = str(pattern).strip().lower()
            if len(pattern_text) == len(status_text) and all(
                    expected in "x*" or expected == actual for expected, actual in zip(pattern_text, status_text)):
                return True
        return False

    @classmethod
    def _report_own_failure(cls, settings: ErrorReportingSettings | None, title: str, details: str | None,
                            reporting_error: BaseException) -> None:
        """Last resort: print, then one plain message straight to the webhook, no throttle"""
        print(f"Error reporting failed while reporting: {title}")
        traceback.print_exc()
        if not settings or not settings.slack_webhook_url:
            return
        try:
            text: str = (f"Error reporting failed ({reporting_error!r}) while reporting: {title}\n"
                         f"{str(details or '')[:1500]}")
            cls._post(url=settings.slack_webhook_url, text=text)
        except BaseException as last_error:
            print(f"Could not send the error reporting failure to Slack either: {last_error!r}")

    @classmethod
    def _post(cls, url: str, text: str) -> None:
        """A Slack incoming webhook: the channel is chosen when the webhook is created"""
        request = urllib.request.Request(url=url, data=json.dumps({"text": text}).encode("utf-8"),
                                         headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=cls.SLACK_TIMEOUT_SECONDS) as response:
            response.read()
