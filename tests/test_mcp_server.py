"""The MCP tools: what a model is told before it calls one, and what it gets back.

The descriptions are load-bearing. A model picks a tool from its description and may never
read the coverage object in the response, so the limits have to be in the text it reads
first. A caveat that only exists in the payload arrives after the reasoning it was meant to
inform.
"""

from __future__ import annotations

from typing import Any

import pytest

from precedent import mcp_server
from precedent.errors import MissingCredential, TooMuchData

types = pytest.importorskip("mcp.types")

EXPECTED = {"award_history", "passthrough_finder", "recipient_profile", "find_program"}


def tools() -> list[Any]:
    return mcp_server.tool_definitions(types)


def schema(tool: Any) -> dict[str, Any]:
    """The schema as a client receives it.

    The Python attribute is ``input_schema`` and the protocol field is ``inputSchema``;
    asserting on the serialized form checks the wire contract rather than the SDK's
    local spelling of it.
    """
    return tool.model_dump(by_alias=True)["inputSchema"]


class TestToolDefinitions:
    def test_the_four_tools_the_spec_names_are_present(self) -> None:
        assert {t.name for t in tools()} == EXPECTED

    def test_every_description_says_counts_are_floors(self) -> None:
        # Not only the pass-through tool: a model may load one description and never see
        # another's, and a floor read as a total is the misreading that matters most here.
        for tool in tools():
            assert "floor" in tool.description.lower(), tool.name
            assert "threshold" in tool.description.lower(), tool.name

    def test_every_description_disclaims_eligibility(self) -> None:
        for tool in tools():
            assert "eligibility determination" in tool.description, tool.name

    def test_each_tool_declares_its_required_arguments(self) -> None:
        required = {t.name: schema(t).get("required", []) for t in tools()}
        assert required["award_history"] == ["program"]
        assert required["passthrough_finder"] == ["state"]
        assert required["recipient_profile"] == ["identifier"]
        assert required["find_program"] == ["query"]

    def test_schemas_are_objects_with_described_properties(self) -> None:
        for tool in tools():
            body = schema(tool)
            assert body["type"] == "object"
            for name, spec in body["properties"].items():
                assert spec.get("description"), f"{tool.name}.{name} has no description"

    def test_the_schema_travels_under_the_protocol_field_name(self) -> None:
        # The SDK calls it input_schema locally and inputSchema on the wire. A client reads
        # the wire name, so that is the one worth pinning.
        wire = tools()[0].model_dump(by_alias=True)
        assert "inputSchema" in wire and wire["inputSchema"]["type"] == "object"


class TestDispatch:
    def test_each_tool_calls_its_api_function_and_returns_the_json_shape(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: dict[str, Any] = {}

        class FakeResult:
            def __init__(self, tag: str) -> None:
                self.tag = tag

            def as_dict(self) -> dict[str, Any]:
                return {"tag": self.tag}

        def record(tag: str):
            def inner(*args: Any, **kwargs: Any) -> FakeResult:
                seen[tag] = (args, kwargs)
                return FakeResult(tag)

            return inner

        from precedent import api

        monkeypatch.setattr(api, "award_history", record("history"))
        monkeypatch.setattr(api, "passthrough", record("passthrough"))
        monkeypatch.setattr(api, "recipient_profile", record("recipient"))
        monkeypatch.setattr(api, "find_programs", record("programs"))

        assert mcp_server.call_tool("award_history", {"program": "93.243"}) == {"tag": "history"}
        assert mcp_server.call_tool("recipient_profile", {"identifier": "X"}) == {
            "tag": "recipient"
        }
        assert mcp_server.call_tool("find_program", {"query": "opioid"}) == {"tag": "programs"}
        assert seen["history"][0] == ("93.243",)
        assert seen["recipient"][0] == ("X",)

    def test_a_state_argument_becomes_the_list_award_history_expects(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}

        class R:
            def as_dict(self) -> dict[str, Any]:
                return {}

        def fake(program: str, **kwargs: Any) -> R:
            captured.update(kwargs)
            return R()

        from precedent import api

        monkeypatch.setattr(api, "award_history", fake)
        mcp_server.call_tool("award_history", {"program": "93.243", "state": "OH"})
        assert captured["states"] == ["OH"]
        mcp_server.call_tool("award_history", {"program": "93.243"})
        assert captured["states"] is None


class TestErrorsComeBackAsAnswers:
    def test_a_missing_argument_names_the_argument(self) -> None:
        # A model can act on "requires the argument 'program'". It cannot act on a KeyError
        # that killed the transport.
        out = mcp_server.call_tool("award_history", {})
        assert "requires the argument 'program'" in out["error"]
        assert out["tool"] == "award_history"
        assert out["disclosure"]

    def test_an_unknown_tool_is_reported_not_raised(self) -> None:
        assert "unknown tool" in mcp_server.call_tool("nonesuch", {})["error"]

    @pytest.mark.parametrize(
        "error",
        [MissingCredential("need a key, here is how"), TooMuchData("narrow the query")],
    )
    def test_a_precedent_error_becomes_an_actionable_payload(
        self, monkeypatch: pytest.MonkeyPatch, error: Exception
    ) -> None:
        from precedent import api

        def boom(*args: Any, **kwargs: Any) -> None:
            raise error

        monkeypatch.setattr(api, "passthrough", boom)
        out = mcp_server.call_tool("passthrough_finder", {"state": "OH"})
        assert out["error"] == str(error)
        assert out["tool"] == "passthrough_finder"
        assert "disclosure" in out


class TestMinSubrecipients:
    def test_the_floor_filters_intermediaries_without_touching_coverage(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Filtering the list must not edit the coverage object: the audits behind the
        # dropped rows were still scanned, and the count of them is what makes the
        # remaining numbers interpretable.
        from dataclasses import dataclass

        from precedent import api

        @dataclass
        class Fake:
            subrecipient_count: int

        class Result:
            def __init__(self) -> None:
                self.intermediaries = [Fake(5), Fake(2), Fake(1)]
                self.coverage = "untouched"

            def as_dict(self) -> dict[str, Any]:
                return {
                    "intermediaries": [i.subrecipient_count for i in self.intermediaries],
                    "coverage": self.coverage,
                }

        class Outcome:
            def __init__(self) -> None:
                self.result = Result()

            def as_dict(self) -> dict[str, Any]:
                return self.result.as_dict()

        monkeypatch.setattr(api, "passthrough", lambda *a, **k: Outcome())
        out = mcp_server.call_tool("passthrough_finder", {"state": "OH", "min_subrecipients": 2})
        assert out["intermediaries"] == [5, 2]
        assert out["coverage"] == "untouched"

    def test_no_floor_keeps_everything(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from precedent import api

        class Outcome:
            def as_dict(self) -> dict[str, Any]:
                return {"intermediaries": "all"}

        monkeypatch.setattr(api, "passthrough", lambda *a, **k: Outcome())
        assert (
            mcp_server.call_tool("passthrough_finder", {"state": "OH"})["intermediaries"] == "all"
        )
