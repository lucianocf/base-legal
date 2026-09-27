import json
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client

from base_legal.config import Settings
from base_legal.corpus.models import Provision, ProvisionKind
from base_legal.corpus.xrefs import CrossReference, find_candidates, resolve
from base_legal.mcp_server.server import build_server
from base_legal.retrieval.search import Hit, SearchResult

ART48 = Provision(
    id="lgpd:art48",
    document_id="lgpd",
    parent_id=None,
    kind=ProvisionKind.ARTICLE,
    label="Art. 48",
    path=("Art. 48",),
    ordinal=0,
    text="O controlador deverá comunicar à autoridade nacional e ao titular a ocorrência de "
    "incidente de segurança que possa acarretar risco ou dano relevante aos titulares.",
)
REVOKED = Provision(
    id="lgpd:art7:par1",
    document_id="lgpd",
    parent_id=None,
    kind=ProvisionKind.PARAGRAPH,
    label="§ 1º",
    path=("Art. 7º", "§ 1º"),
    ordinal=1,
    text="",
    revoked=True,
)


ART52 = Provision(
    id="lgpd:art52:par1:incVIII",
    document_id="lgpd",
    parent_id=None,
    kind=ProvisionKind.INCISO,
    label="VIII",
    path=("Art. 52", "§ 1º", "VIII"),
    ordinal=2,
    text="a pronta adoção de medidas corretivas, observado o art. 48 desta Lei;",
)


class _Backend:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def search(self, question: str, k: int) -> SearchResult:
        self.questions.append(question)
        missing = ("lgpd:art99",) if "99" in question else ()
        return SearchResult(
            hits=(Hit(ART48, 0.03),), best_similarity=0.7, missing_references=missing
        )

    def provision(self, provision_id: str) -> Provision | None:
        return {p.id: p for p in (ART48, ART52, REVOKED)}.get(provision_id)

    def references(self, texts: Mapping[str, str]) -> dict[str, tuple[CrossReference, ...]]:
        existing = {ART48.id}
        return {pid: resolve(pid, find_candidates(pid, t), existing) for pid, t in texts.items()}


def _call(backend: _Backend, tool: str, args: dict[str, Any]) -> Any:
    async def go() -> Any:
        async with Client(build_server(backend, Settings())) as client:
            return await client.call_tool(tool, args)

    return anyio.run(go)


def _structured(result: Any) -> dict[str, Any]:
    assert not result.is_error, result
    if result.structured_content is not None:
        return dict(result.structured_content)
    return dict(json.loads(result.content[0].text))


def test_exactly_three_read_only_tools() -> None:
    # OWASP LLM06: no tool with side effects; the MCP server is read-only.
    async def go() -> Any:
        async with Client(build_server(_Backend(), Settings())) as client:
            return await client.list_tools()

    tools = anyio.run(go).tools
    assert {t.name for t in tools} == {"search_provisions", "get_provision", "verify_citation"}
    for tool in tools:
        assert tool.annotations is not None
        assert tool.annotations.read_only_hint is True
        assert tool.annotations.destructive_hint is False
        assert tool.annotations.idempotent_hint is True
        assert tool.annotations.open_world_hint is False


def test_search_provisions_redacts_and_reports() -> None:
    backend = _Backend()
    out = _structured(
        _call(
            backend,
            "search_provisions",
            {"question": "Vazou o CPF 529.982.247-25; preciso avisar?", "k": 3},
        )
    )
    assert out["hits"][0]["provision"]["id"] == "lgpd:art48"
    assert out["no_support"] is False
    assert "aconselhamento jurídico" in out["disclaimer"]
    assert backend.questions == ["Vazou o CPF [CPF_1]; preciso avisar?"]

    missing = _structured(_call(backend, "search_provisions", {"question": "O que diz o art. 99?"}))
    assert missing["missing_references"] == ["lgpd:art99"]
    assert missing["no_support"] is True


@pytest.mark.parametrize(
    "args",
    [
        {"question": "x", "k": 0},
        {"question": "x", "k": 21},
        {"question": "  "},
        {"question": "a" * 50_000},
    ],
)
def test_search_limits(args: dict[str, Any]) -> None:
    backend = _Backend()
    assert _call(backend, "search_provisions", args).is_error
    assert backend.questions == []


def test_get_provision() -> None:
    backend = _Backend()
    out = _structured(_call(backend, "get_provision", {"provision_id": "lgpd:art48"}))
    assert out["found"] is True
    assert out["in_force"] is True
    assert out["provision"]["text"] == ART48.text
    assert (
        _structured(_call(backend, "get_provision", {"provision_id": "lgpd:art99"}))["found"]
        is False
    )
    assert (
        _structured(_call(backend, "get_provision", {"provision_id": "lgpd:art7:par1"}))["in_force"]
        is False
    )
    assert _call(backend, "get_provision", {"provision_id": "Art. 48"}).is_error


def test_get_provision_lists_its_cross_references() -> None:
    args = {"provision_id": "lgpd:art52:par1:incVIII"}
    provision = _structured(_call(_Backend(), "get_provision", args))["provision"]
    [reference] = provision["references"]
    assert reference["target"] == "lgpd:art48"
    assert provision["text"][reference["start"] : reference["end"]] == "art. 48 desta Lei"


@pytest.mark.parametrize(
    ("provision_id", "quote", "issue"),
    [
        ("lgpd:art48", "comunicar à autoridade nacional e ao titular", None),
        ("lgpd:art48", "comunicar apenas se quiser", "quote_not_found"),
        ("lgpd:art99", "qualquer texto aqui", "unknown_id"),
        ("lgpd:art7:par1", "qualquer texto aqui", "revoked"),
        ("not an id", "qualquer texto aqui", "malformed_id"),
    ],
)
def test_verify_citation(provision_id: str, quote: str, issue: str | None) -> None:
    out = _structured(
        _call(_Backend(), "verify_citation", {"provision_id": provision_id, "quote": quote})
    )
    assert out["valid"] is (issue is None)
    assert out["issue"] == issue


def test_server_module_never_imports_the_anthropic_sdk() -> None:
    import base_legal.mcp_server.server as server

    source = Path(server.__file__).read_text(encoding="utf-8")
    assert "anthropic" not in source
    assert "generation.answer import DISCLAIMER, ProvisionView" in source  # data only
    assert "base_legal.mcp_server.server" in sys.modules
