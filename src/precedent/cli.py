"""The command-line surface. A thin adapter over the library.

Business logic in a command handler is a bug: the concrete test from the build prompt is
whether a feature can be called from the MCP server without copying code. Everything these
commands do beyond parsing arguments and choosing a renderer belongs in ``api.py``.

Milestone 0 ships the entry point and nothing else. The commands arrive with the modules
they adapt: ``history`` at M3, ``passthrough`` at M5, ``programs`` at M2, ``cache`` at M1.
"""

from __future__ import annotations

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
