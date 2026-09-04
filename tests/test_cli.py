"""The entry point exists, reports its version, and carries the required disclosure."""

from __future__ import annotations

from click.testing import CliRunner

from precedent import DISCLOSURE, __version__
from precedent.cli import main


def test_version_matches_the_package_and_names_the_program() -> None:
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
    assert "precedent" in result.output


def test_help_says_history_needs_no_key_and_passthrough_does() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "no account and no key" in result.output
    assert "Federal Audit Clearinghouse" in result.output


def test_the_disclosure_is_verbatim_and_available_to_every_renderer() -> None:
    result = CliRunner().invoke(main, ["disclosure"])
    assert result.exit_code == 0
    assert result.output.strip() == DISCLOSURE
    for required in (
        "informational only",
        "not an eligibility determination",
        "not legal, tax, or accounting advice",
        "Verify against the official source",
    ):
        assert required in DISCLOSURE
