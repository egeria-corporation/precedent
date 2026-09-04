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


def test_cache_info_reports_the_store_and_the_ttls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRECEDENT_CACHE_DIR", str(tmp_path))
    result = CliRunner().invoke(main, ["cache", "info"])
    assert result.exit_code == 0
    assert str(tmp_path) in result.output
    assert "entries  0" in result.output
    assert "usaspending 168h" in result.output


def test_cache_clear_asks_first_and_reports_what_it_removed(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRECEDENT_CACHE_DIR", str(tmp_path))
    from precedent.cache import Cache, cache_key

    with Cache(tmp_path) as store:
        store.put(cache_key("fac", "GET", "/a"), source="fac", status=200, body=b"{}")

    runner = CliRunner()
    declined = runner.invoke(main, ["cache", "clear"], input="n\n")
    assert declined.exit_code != 0, "declining must not empty the cache"
    with Cache(tmp_path) as store:
        assert store.info().entries == 1

    cleared = runner.invoke(main, ["cache", "clear", "--yes"])
    assert cleared.exit_code == 0
    assert "cleared 1 entries" in cleared.output
    with Cache(tmp_path) as store:
        assert store.info().entries == 0


def test_cache_clear_on_an_empty_store_says_so(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("PRECEDENT_CACHE_DIR", str(tmp_path))
    result = CliRunner().invoke(main, ["cache", "clear"])
    assert result.exit_code == 0
    assert "already empty" in result.output
