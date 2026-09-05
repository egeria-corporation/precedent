"""Capture a real upstream response into ``tests/fixtures``, with its provenance.

Mocked-shape tests do not catch schema drift, and schema drift is the failure mode that
actually matters for a tool that is a thin layer over somebody else's API. So the tests run
against real responses, and this is what captures them.

Every capture writes two files: the response body, and a ``.meta.json`` sidecar recording
the endpoint, the exact request, the retrieval date and the status. A fixture whose origin
nobody can reconstruct is a fixture nobody can refresh.

    python -m precedent.devtools.capture_fixture \\
        --name usaspending_autocomplete_opioid \\
        --url https://api.usaspending.gov/api/v2/autocomplete/cfda/ \\
        --source usaspending --method POST \\
        --body '{"search_text": "opioid", "limit": 5}' \\
        --trim results:5
"""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from precedent.config import Config
from precedent.http import HttpClient

FIXTURES = Path(__file__).resolve().parents[3] / "tests" / "fixtures"


def trim(body: Any, rules: list[str]) -> Any:
    """Cut list fields down to size, so a fixture stays reviewable in a pull request.

    Each rule is ``key:n``, applied to the top level of a JSON object. Trimming is recorded
    in the sidecar, because a trimmed fixture is no longer byte-identical to the response
    and a reader deserves to know that.
    """
    for rule in rules:
        key, _, count = rule.partition(":")
        if isinstance(body, dict) and isinstance(body.get(key), list):
            body[key] = body[key][: int(count or 5)]
    return body


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--name", required=True, help="Fixture file stem, no extension.")
    ap.add_argument("--url", required=True)
    ap.add_argument("--source", required=True, choices=["usaspending", "fac", "opengrants"])
    ap.add_argument("--method", default="POST", choices=["GET", "POST"])
    ap.add_argument("--body", default=None, help="JSON request body for POST.")
    ap.add_argument("--params", default=None, help="JSON query parameters for GET.")
    ap.add_argument("--trim", action="append", default=[], help="Trim a list field: key:n")
    ap.add_argument("--out", default=str(FIXTURES))
    args = ap.parse_args()

    body = json.loads(args.body) if args.body else None
    params = json.loads(args.params) if args.params else None
    config = Config.from_env()
    headers = {}
    if args.source == "fac" and config.fac_api_key:
        headers["X-Api-Key"] = config.fac_api_key

    with HttpClient(config) as http:
        response = http.request(
            args.source,
            args.method,
            args.url,
            json_body=body,
            params=params,
            headers=headers or None,
            no_cache=True,
        )

    parsed = trim(response.json(), args.trim)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{args.name}.json").write_text(
        json.dumps(parsed, indent=2, sort_keys=False) + "\n", encoding="utf-8"
    )
    (out_dir / f"{args.name}.meta.json").write_text(
        json.dumps(
            {
                "source": args.source,
                "endpoint": args.url,
                "method": args.method,
                "request_body": body,
                "request_params": params,
                "status": response.status,
                "retrieved": datetime.now(UTC).isoformat(timespec="seconds"),
                "trimmed": args.trim or None,
                "note": "Captured by precedent.devtools.capture_fixture. Trimmed fixtures are "
                "not byte-identical to the upstream response.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"{args.name}: HTTP {response.status}, {len(json.dumps(parsed)):,} bytes after trim")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
