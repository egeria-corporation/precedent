"""Typed exceptions whose messages tell the reader what to do next.

The build prompt is specific about one of these: a missing Federal Audit Clearinghouse key
must not surface as a ``KeyError`` or a stack trace. It must say where to get a key, that it
is free, and that it takes two minutes. The rest follow the same rule, because an error a
user cannot act on is a bug report we will receive instead.
"""

from __future__ import annotations

FAC_SIGNUP_URL = "https://www.fac.gov/api/signup/"


class PrecedentError(Exception):
    """Base for every error this tool raises deliberately."""


class MissingCredential(PrecedentError):
    """A command needs a key the user has not set."""


class UpstreamError(PrecedentError):
    """An upstream API failed in a way retrying did not fix."""

    def __init__(self, source: str, status: int | None, detail: str) -> None:
        self.source, self.status, self.detail = source, status, detail
        where = f"{source} returned HTTP {status}" if status else f"{source} was unreachable"
        super().__init__(f"{where}: {detail}")


class TooMuchData(PrecedentError):
    """The requested pull is larger than a record-by-record fetch can honestly serve.

    Raised instead of hanging for ten minutes. The message names the narrower query that
    would work, because "too many results" without a next step is not an answer.
    """


def fac_key_missing() -> MissingCredential:
    """The message a user sees when a pass-through command needs a key and finds none."""
    return MissingCredential(
        "This command needs a Federal Audit Clearinghouse API key, which is free and takes "
        "about two minutes to get.\n"
        f"  1. Go to {FAC_SIGNUP_URL}\n"
        "  2. Enter your name and email address. That is the whole process.\n"
        "  3. The key arrives by email from api.data.gov, usually within a minute.\n"
        "Then set FAC_API_KEY in your environment, or put it in a .env file beside your "
        "project.\n"
        "Award history commands such as `precedent history` need no key and work now."
    )
