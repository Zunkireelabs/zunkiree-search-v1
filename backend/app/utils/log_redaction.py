"""Keep what a student typed (and the id that unlocks their chat) out of the logs.

Education only: other tenants keep their existing log lines, which clinic and Instagram debugging relies on.
"""
import logging
import re

# GET /api/v1/widget/history/<site_id>/<session_id>: whoever holds the session id can read that chat.
_HISTORY_PATH = re.compile(r"(/widget/history/[^/?\s]+)/[^/?\s]+")


def question_for_log(website_type: str | None, question: str) -> str:
    """The question as it may appear in a log line: its length only for education, the first 80 characters otherwise."""
    if website_type == "education":
        return f"<{len(question)} chars>"
    return repr(question[:80])


def redact_session_in_path(path: str) -> str:
    return _HISTORY_PATH.sub(r"\1/<session>", path)


class SessionPathRedactionFilter(logging.Filter):
    """On uvicorn's access log, hides the session id in the history URL. Never drops a record."""

    def filter(self, record: logging.LogRecord) -> bool:
        # uvicorn logs '%s - "%s %s HTTP/%s" %d' with args (client, method, path, http_version, status)
        if isinstance(record.args, tuple) and len(record.args) == 5 and isinstance(record.args[2], str):
            args = list(record.args)
            args[2] = redact_session_in_path(args[2])
            record.args = tuple(args)
        return True


def install_access_log_redaction() -> None:
    access_log = logging.getLogger("uvicorn.access")
    if not any(isinstance(f, SessionPathRedactionFilter) for f in access_log.filters):
        access_log.addFilter(SessionPathRedactionFilter())
