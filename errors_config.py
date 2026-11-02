from synchedconfig.errors import SynchedConfigNotFoundError
from synchedconfig.synched_config import SynchedConfig


class ErrorsDatabaseSettings:
    """Where the throttle state is kept"""

    def __init__(self, host: str, user: str, password: str, database: str, schema: str, port: int = 5432):
        self.host: str = host
        self.user: str = user
        self.password: str = password
        self.database: str = database
        self.schema: str = schema
        self.port: int = port


class ErrorReportingSettings:
    """servelamb_errors.yaml. See servelamb_errors.sample.yaml for every setting"""

    def __init__(self, slack_webhook_url: str = "", environment_label: str = "", throttle_minutes: float = 0,
                 report_status_codes: list[str] | None = None, slack_mention: str = "",
                 database: ErrorsDatabaseSettings | None = None, log_retention_days: int = 10):
        """A Slack incoming webhook; its channel (the recipient) is chosen when the webhook is created. Empty: off"""
        self.slack_webhook_url: str = slack_webhook_url
        """Shown at the start of every message, e.g. "prod" """
        self.environment_label: str = environment_label
        """At most one message per kind of error in this many minutes. 0 sends every error"""
        self.throttle_minutes: float = throttle_minutes
        """Response statuses report_response sends. Exact codes or patterns where x or * is any digit"""
        self.report_status_codes: list[str] = report_status_codes or []
        """Put in front of every message, e.g. "<!channel>" or "<@U012AB3CD>" to notify someone"""
        self.slack_mention: str = slack_mention
        """Where the throttle state is kept. None: no throttle, every error is sent"""
        self.database: ErrorsDatabaseSettings | None = database
        """How many days of errors error_log keeps"""
        self.log_retention_days: int = log_retention_days


class ErrorsConfig(SynchedConfig):
    """
    servelamb_errors.yaml, found the same way as any SynchedConfig: next to synchedconfig and up to three
    directories above it (on Lambda, the root of the package), merged with a copy on USB when remote_dirs are set.
    Read once per process: settings never change after start up. A missing file turns error reporting off.
    An app can point at another file (e.g. one per environment) by setting config_file_name before the first report.
    """
    config_file_name: str = "servelamb_errors.yaml"
    remote_dirs: list[str] = []
    _settings: ErrorReportingSettings | None = None

    @classmethod
    def settings(cls) -> ErrorReportingSettings:
        if cls._settings:
            return cls._settings
        try:
            data = cls.load()
        except SynchedConfigNotFoundError as not_found:
            print(f"servelamb_errors: error reporting is off. {not_found}")
            cls._settings = ErrorReportingSettings()
            return cls._settings
        db: dict = data.get("database") or {}
        database: ErrorsDatabaseSettings | None = ErrorsDatabaseSettings(
            host=db.get("host") or "",
            user=db.get("user") or "",
            password=db.get("password") or "",
            database=db.get("database") or "",
            schema=db.get("schema") or "public",
            port=int(db.get("port") or 5432),
        ) if db.get("host") else None
        cls._settings = ErrorReportingSettings(
            slack_webhook_url=(data.get("slack_webhook_url") or "").strip(),
            environment_label=data.get("environment_label") or "",
            throttle_minutes=float(data.get("throttle_minutes") or 0),
            report_status_codes=[str(code) for code in data.get("report_status_codes") or ["4xx", "5xx"]],
            slack_mention=data.get("slack_mention") or "",
            database=database,
            log_retention_days=int(data.get("log_retention_days") or 10),
        )
        return cls._settings
