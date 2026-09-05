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
