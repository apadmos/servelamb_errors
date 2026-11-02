"""
Reports an app's own errors to Slack. Settings: servelamb_errors.yaml, found like any SynchedConfig
(see ErrorsConfig and servelamb_errors.sample.yaml). Hook these into the app's server file:

    import servelamb_errors
    lambda_host = LambdaHosting(on_error=servelamb_errors.report_exception)   exceptions while handling a request
    def before_response(req, resp):
        servelamb_errors.report_response(req=req, resp=resp)                  error statuses (404, 500...)
    servelamb_errors.report(kind="startup", title=..., details=..., urgent=True)   a failed start up

The throttle table is created with: python -m servelamb_errors.errors_db
"""
from .error_reporter import ErrorReporter


def report(kind: str, title: str, details: str | None = None, urgent: bool = False) -> None:
    ErrorReporter.report(kind=kind, title=title, details=details, urgent=urgent)


def report_exception(title: str, details: str | None = None, urgent: bool = False) -> None:
    """For LambdaHosting(on_error=...)"""
    ErrorReporter.report(kind="exception", title=title, details=details, urgent=urgent)


def report_response(req, resp) -> None:
    ErrorReporter.report_response(req=req, resp=resp)
