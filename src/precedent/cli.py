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


@main.command("disclosure")
def disclosure() -> None:
    """Print the disclosure that appears in the footer of every command's output."""
    _emit(DISCLOSURE)


if __name__ == "__main__":
    main()
