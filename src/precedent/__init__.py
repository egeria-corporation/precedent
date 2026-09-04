"""Federal award history and pass-through finder.

Two questions, one tool. Who has actually won a federal program before, so a first-time
applicant can see the new-entrant rate rather than guess at it; and which state agencies,
universities and large nonprofits pass federal money down to organizations too small to win
it directly, which lives in single audit filings and is in no commercial product.

The tool is thin on purpose: API composition over two documented federal endpoints plus a
statistics layer. There is no database, no ingest pipeline and no warehouse here.
"""

from __future__ import annotations

__version__ = "0.1.0"

# The required disclosure. It appears verbatim in the footer of every command's output, in
# every format, including JSON. It is defined once so it cannot drift between renderers.
DISCLOSURE = (
    "This is informational only, derived from public data on the dates shown. It is not an "
    "eligibility determination, and not legal, tax, or accounting advice. Verify against the "
    "official source before relying on it."
)

__all__ = ["DISCLOSURE", "__version__"]
