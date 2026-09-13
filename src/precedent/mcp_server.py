"""The MCP server: four tools over stdio, each a thin call into ``api.py``.

Every tool returns exactly what ``--json`` returns, because the CLI and this server are
adapters over the same library and a model that reads one should not get a different answer
than a person who reads the other.

The tool *descriptions* carry the limitations, not just the payloads. A model choosing a
tool reads the description and may never look at the ``coverage`` object it gets back, so
the two facts that most change how an answer should be used - that pass-through counts are
floors, and that nothing here is an eligibility determination - are stated in the text the
model sees before it decides anything. A caveat only present in the response is a caveat
that arrives after the reasoning it was supposed to inform.

The ``mcp`` package is an optional dependency; importing this module without it raises a
message saying how to install it rather than a bare ImportError.
"""

from __future__ import annotations

import json
from typing import Any

from precedent import DISCLOSURE
from precedent.errors import PrecedentError

SERVER_NAME = "precedent"

# Appended to every tool description. Repetition is deliberate: a model may load one tool's
# description and never see another's.
LIMITS = (
    " Pass-through subrecipient counts are floors, never totals: single audits are filed "
    "only by organizations spending at or above the federal threshold, so everyone below it "
    "is absent from the data rather than counted as zero. No output from this tool is an "
    "eligibility determination, a prediction, or advice; it is a description of what public "
    "records show, with its retrieval date attached."
)


def _require_mcp() -> Any:
    try:
        import mcp.types as types
        from mcp.server import Server
        from mcp.server.stdio import stdio_server
    except ImportError as error:  # pragma: no cover - exercised by hand, not in CI
        raise PrecedentError(
            "The MCP server needs the optional `mcp` package.\n"
            "  uvx --from 'federal-precedent[mcp]' precedent mcp\n"
            "or, if precedent is installed: pip install 'federal-precedent[mcp]'"
        ) from error
    return types, Server, stdio_server


def tool_definitions(types: Any) -> list[Any]:
    """The four tools, with their limitations in the text a model actually reads."""
    return [
        types.Tool(
            name="award_history",
            description=(
                "Who has won a federal grant program before, and how open it is to newcomers. "
                "Returns the new-entrant rate (the share of recipients in the window that had "
                "won nothing under this program in the preceding lookback), award size "
                "percentiles, repeat winners, concentration, and geography, for one "
                "Assistance Listing number such as 93.243." + LIMITS
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "program": {
                        "type": "string",
                        "description": "Assistance Listing number, e.g. '93.243'.",
                    },
                    "since_fy": {
                        "type": "integer",
                        "description": "First federal fiscal year. Default: five complete years back.",
                    },
                    "until_fy": {
                        "type": "integer",
                        "description": "Last federal fiscal year. Default: the last complete one.",
                    },
                    "lookback_years": {
                        "type": "integer",
                        "description": "Years before the window used to decide who is new. Default 5.",
                    },
                    "state": {
                        "type": "string",
                        "description": "Two-letter code, to limit to recipients in one state.",
                    },
                },
                "required": ["program"],
            },
        ),
        types.Tool(
            name="passthrough_finder",
            description=(
                "Which organizations actually hand federal money to nonprofits in one state. "
                "USAspending records the award to a state agency and not the subawards it "
                "makes; this reads single audits, where a subrecipient's own auditor names "
                "who passed the money. Ranked by how many distinct organizations name each "
                "intermediary, because that answers who makes subawards to organizations "
                "like the one asking." + LIMITS
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {"type": "string", "description": "Two-letter state code, e.g. 'OH'."},
                    "program": {
                        "type": "string",
                        "description": "Assistance Listing number to narrow to, e.g. '93.045'.",
                    },
                    "since_audit_year": {
                        "type": "integer",
                        "description": "First audit year. Coverage begins at 2016.",
                    },
                    "until_audit_year": {"type": "integer", "description": "Last audit year."},
                    "min_subrecipients": {
                        "type": "integer",
                        "description": "Drop intermediaries named by fewer organizations than this.",
                    },
                },
                "required": ["state"],
            },
        ),
        types.Tool(
            name="recipient_profile",
            description=(
                "One organization, by Unique Entity Identifier, Employer Identification "
                "Number, or name: its direct federal awards, its single audits and total "
                "federal expenditures, who passes money to it, and whether it passes money "
                "down. An EIN reaches further back than a UEI, because audits migrated from "
                "the legacy collection carry a placeholder in the UEI column. A name is "
                "matched loosely and may combine organizations." + LIMITS
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "identifier": {
                        "type": "string",
                        "description": "A UEI, an EIN, or an organization name.",
                    }
                },
                "required": ["identifier"],
            },
        ),
        types.Tool(
            name="find_program",
            description=(
                "Find an Assistance Listing number by keyword or partial number, so the other "
                "tools can be called with one. Matches a contiguous substring of the listing "
                "title, so single words work better than phrases." + LIMITS
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Keyword such as 'opioid', or a partial number like '93.2'.",
                    },
                    "limit": {"type": "integer", "description": "Maximum listings. Default 20."},
                },
                "required": ["query"],
            },
        ),
    ]


def call_tool(name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Dispatch to ``api.py`` and return the same shape ``--json`` prints.

    Errors come back as a payload rather than an exception, so a model gets an actionable
    sentence - a missing key, a query that is too broad - instead of a transport failure it
    cannot interpret.
    """
    from precedent import api

    args = arguments or {}
    try:
        if name == "award_history":
            return api.award_history(
                args["program"],
                since_fy=args.get("since_fy"),
                until_fy=args.get("until_fy"),
                lookback_years=args.get("lookback_years", 5),
                states=[args["state"]] if args.get("state") else None,
            ).as_dict()
        if name == "passthrough_finder":
            outcome = api.passthrough(
                args["state"],
                program=args.get("program"),
                since_audit_year=args.get("since_audit_year"),
                until_audit_year=args.get("until_audit_year"),
            )
            floor = int(args.get("min_subrecipients") or 0)
            if floor > 1:
                outcome.result.intermediaries = [
                    i for i in outcome.result.intermediaries if i.subrecipient_count >= floor
                ]
            return outcome.as_dict()
        if name == "recipient_profile":
            return api.recipient_profile(args["identifier"]).as_dict()
        if name == "find_program":
            return api.find_programs(args["query"], limit=int(args.get("limit") or 20)).as_dict()
    except PrecedentError as error:
        return {"error": str(error), "tool": name, "disclosure": DISCLOSURE}
    except KeyError as error:
        return {
            "error": f"{name} requires the argument {error}",
            "tool": name,
            "disclosure": DISCLOSURE,
        }
    return {"error": f"unknown tool {name!r}", "disclosure": DISCLOSURE}


async def serve() -> None:  # pragma: no cover - transport, exercised by hand
    """Run the server over stdio until the client disconnects."""
    types, Server, stdio_server = _require_mcp()
    server = Server(SERVER_NAME)

    @server.list_tools()
    async def list_tools() -> list[Any]:
        return tool_definitions(types)

    @server.call_tool()
    async def handle(name: str, arguments: dict[str, Any]) -> list[Any]:
        payload = call_tool(name, arguments)
        return [types.TextContent(type="text", text=json.dumps(payload, indent=2, default=str))]

    async with stdio_server() as (read, write):
        await server.run(read, write, server.create_initialization_options())


def main() -> None:  # pragma: no cover - entry point
    import asyncio

    asyncio.run(serve())
