"""The command-line surface. A thin adapter over the library.

Business logic in a command handler is a bug: the concrete test from the build prompt is
whether a feature can be called from the MCP server without copying code. Everything these
commands do beyond parsing arguments and choosing a renderer belongs in ``api.py``.

Milestone 0 ships the entry point and nothing else. The commands arrive with the modules
they adapt: ``history`` at M3, ``passthrough`` at M5, ``programs`` at M2, ``cache`` at M1.
"""

from __future__ import annotations

import sys

import click

from precedent import DISCLOSURE, __version__


def _emit(line: str = "") -> None:
    """One place that writes to stdout, so tests capture and renderers share it."""
    click.echo(line)


@click.group()
@click.version_option(__version__, prog_name="precedent")
def main() -> None:
    """Federal award history and pass-through finder.

    `precedent history` works with no account and no key. `precedent passthrough` needs a
    free Federal Audit Clearinghouse key; the command says where to get one when it is
    missing.
    """


@main.command("history")
@click.argument("program")
@click.option(
    "--since", type=int, default=None, help="First fiscal year. Default: five complete years back."
)
@click.option(
    "--until", type=int, default=None, help="Last fiscal year. Default: the last complete one."
)
@click.option(
    "--lookback",
    type=int,
    default=5,
    show_default=True,
    help="Lookback years for the new-entrant rate.",
)
@click.option(
    "--state", "states", multiple=True, help="Limit to recipients in a state. Repeatable."
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--no-cache", is_flag=True, help="Ignore anything already cached.")
def history(
    program: str,
    since: int | None,
    until: int | None,
    lookback: int,
    states: tuple[str, ...],
    as_json: bool,
    no_cache: bool,
) -> None:
    """Award history and the new-entrant rate for one Assistance Listing.

    
      precedent history 93.243
      precedent history 16.842 --since 2020 --until 2024
      precedent history 93.243 --state OH --json

    Needs no account and no key.
    """
    import json as jsonlib

    from precedent.api import award_history
    from precedent.config import Config
    from precedent.errors import PrecedentError
    from precedent.http import HttpClient
    from precedent.render import render_history

    config = Config.from_env()
    try:
        with HttpClient(config) as http:
            result = award_history(
                program,
                since_fy=since,
                until_fy=until,
                lookback_years=lookback,
                states=list(states) or None,
                config=config,
                http=http,
                no_cache=no_cache or None,
            )
    except PrecedentError as error:
        _emit(f"STOP: {error}")
        sys.exit(4)

    if as_json:
        _emit(jsonlib.dumps(result.as_dict(), indent=2, default=str))
        return
    _emit(render_history(result))


@main.command("passthrough")
@click.option("--state", required=True, help="Two-letter state code, e.g. OH. Required.")
@click.option("--program", default=None, help="Assistance Listing number, e.g. 93.045.")
@click.option("--since", type=int, default=None, help="First audit year. Default: five back.")
@click.option("--until", type=int, default=None, help="Last audit year. Default: last year.")
@click.option(
    "--fuzzy",
    is_flag=True,
    help="Also merge near-identical names. Off by default; a wrong merge states a falsehood.",
)
@click.option(
    "--show-name-variants",
    is_flag=True,
    help="Print every raw spelling merged into each cluster. Always in --json.",
)
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--no-cache", is_flag=True, help="Ignore anything already cached.")
def passthrough_cmd(
    state: str,
    program: str | None,
    since: int | None,
    until: int | None,
    fuzzy: bool,
    show_name_variants: bool,
    as_json: bool,
    no_cache: bool,
) -> None:
    """Who passes federal money down to organizations in one state.

    
      precedent passthrough --state OH --program 93.045
      precedent passthrough --state OH --show-name-variants
      precedent passthrough --state CA --program 93.243 --json

    Needs a free Federal Audit Clearinghouse key in FAC_API_KEY. Every count is a floor:
    organizations under the single audit threshold file nothing and are absent entirely.
    """
    import json as jsonlib

    from precedent.api import passthrough as run_passthrough
    from precedent.config import Config
    from precedent.errors import PrecedentError
    from precedent.http import HttpClient
    from precedent.render import render_passthrough

    config = Config.from_env()
    try:
        with HttpClient(config) as http:
            outcome = run_passthrough(
                state,
                program=program,
                since_audit_year=since,
                until_audit_year=until,
                fuzzy=fuzzy,
                config=config,
                http=http,
                no_cache=no_cache or None,
            )
    except PrecedentError as error:
        _emit(f"STOP: {error}")
        sys.exit(4)

    if as_json:
        _emit(jsonlib.dumps(outcome.as_dict(), indent=2, default=str))
        return
    _emit(render_passthrough(outcome, show_name_variants=show_name_variants))


@main.command("recipient")
@click.argument("identifier")
@click.option("--json", "as_json", is_flag=True, help="Machine-readable output.")
@click.option("--no-cache", is_flag=True, help="Ignore anything already cached.")
def recipient(identifier: str, as_json: bool, no_cache: bool) -> None:
    """One organization, by UEI, EIN, or name.

    
      precedent recipient JE73CDQUAPA7
      precedent recipient 54-1939556
      precedent recipient "Feeding Southwest Virginia" --json

    An EIN reaches further back than a UEI: audits migrated from the legacy collection
    carry a placeholder in the UEI column. Works without a FAC key, with less in it.
    """
    import json as jsonlib

    from precedent.api import recipient_profile
    from precedent.config import Config
    from precedent.errors import PrecedentError
    from precedent.http import HttpClient
    from precedent.render import render_recipient

    config = Config.from_env()
    try:
        with HttpClient(config) as http:
            outcome = recipient_profile(
                identifier, config=config, http=http, no_cache=no_cache or None
            )
    except PrecedentError as error:
        _emit(f"STOP: {error}")
        sys.exit(4)

    if as_json:
        _emit(jsonlib.dumps(outcome.as_dict(), indent=2, default=str))
        return
    _emit(render_recipient(outcome))


@main.command("mcp")
def mcp() -> None:
    """Run the Model Context Protocol server over stdio.

    Exposes award_history, passthrough_finder, recipient_profile and find_program as tools,
    each returning exactly what `--json` returns. Needs the optional `mcp` extra:

    
      uvx --from 'federal-precedent[mcp]' precedent mcp
    """
    from precedent.errors import PrecedentError

    try:
        from precedent.mcp_server import main as serve

        serve()
    except PrecedentError as error:
        _emit(f"STOP: {error}")
        sys.exit(4)
    except KeyboardInterrupt:  # pragma: no cover
        pass


@main.command("programs")
@click.argument("search_text")
@click.option("--limit", default=20, show_default=True, help="How many listings to return.")
@click.option("--no-cache", is_flag=True, help="Ignore anything already cached.")
def programs(search_text: str, limit: int, no_cache: bool) -> None:
    """Find an Assistance Listing by keyword or partial number.

    
      precedent programs "opioid treatment"
      precedent programs 93.2
    """
    from precedent.config import Config
    from precedent.errors import PrecedentError
    from precedent.http import HttpClient
    from precedent.sources.usaspending import UsaSpending

    config = Config.from_env()
    try:
        with HttpClient(config) as http:
            result = UsaSpending(http).find_programs(
                search_text, limit=limit, no_cache=no_cache or None
            )
    except PrecedentError as error:
        _emit(f"STOP: {error}")
        sys.exit(4)

    if not result.programs:
        _emit(f"No Assistance Listing matches {search_text!r}.")
        _emit("The search matches a run of characters in the listing title, so try one word,")
        _emit("or a partial number such as 93.2.")
        return
    if result.fell_back:
        _emit(
            f"Nothing matches the whole phrase {search_text!r}; showing matches for "
            f"{result.matched_term!r}."
        )
        _emit("")
    width = max(len(p.number) for p in result.programs)
    for program in result.programs:
        _emit(f"{program.number:<{width}}  {program.title or ''}")
    _emit("")
    plural = "" if len(result.programs) == 1 else "s"
    _emit(
        f"{len(result.programs)} listing{plural} from USAspending, "
        f"retrieved {result.retrieved.date().isoformat()}."
    )
    _emit(DISCLOSURE)


@main.group()
def cache() -> None:
    """The local response cache: where it is, how big, how old."""


@cache.command("info")
def cache_info() -> None:
    """Print the cache path, entry count, size, and the age of what it holds."""
    from precedent.cache import Cache
    from precedent.config import Config

    cfg = Config.from_env()
    with Cache(cfg.cache_dir) as store:
        i = store.info()
    _emit(f"path     {i.path}")
    _emit(f"entries  {i.entries:,}")
    _emit(f"size     {i.bytes_on_disk / 1e6:,.1f} MB")
    _emit(f"oldest   {i.oldest.isoformat(timespec='seconds') if i.oldest else '-'}")
    _emit(f"newest   {i.newest.isoformat(timespec='seconds') if i.newest else '-'}")
    ttls = ", ".join(f"{k} {v}h" for k, v in sorted(cfg.ttl_hours.items()))
    _emit(f"ttl      {ttls}")


@cache.command("clear")
@click.option("--yes", is_flag=True, help="Do not ask for confirmation.")
def cache_clear(yes: bool) -> None:
    """Empty the cache. The next command refetches what it needs."""
    from precedent.cache import Cache
    from precedent.config import Config

    cfg = Config.from_env()
    with Cache(cfg.cache_dir) as store:
        n = store.info().entries
        if not n:
            _emit("cache is already empty")
            return
        if not yes:
            click.confirm(f"Delete {n:,} cached responses from {store.path}?", abort=True)
        _emit(f"cleared {store.clear():,} entries")


@main.command("disclosure")
def disclosure() -> None:
    """Print the disclosure that appears in the footer of every command's output."""
    _emit(DISCLOSURE)


if __name__ == "__main__":
    main()
