import os
import sys
from pathlib import Path
from typing import Any

import anyio
import pytest
from mcp import Client, StdioServerParameters

from base_legal.config import IngestMode
from base_legal.corpus.manifest import Manifest
from base_legal.corpus.models import Document
from base_legal.embeddings.providers import HashingEmbedder
from base_legal.ingest import ingest_documents
from base_legal.store.db import Store

pytestmark = pytest.mark.integration

GUARD = """
import anthropic, sys
class _Forbidden:
    def __init__(self, *a, **k):
        raise SystemExit("the MCP server must never construct an Anthropic client")
anthropic.Anthropic = _Forbidden
from base_legal.mcp_server.server import main
main()
"""


def test_stdio_server_end_to_end(
    store: Store, database_url: str, document: Document, manifest: Manifest, tmp_path: Path
) -> None:
    ingest_documents(
        store,
        [document],
        manifest,
        embeddings_dir=tmp_path,
        mode=IngestMode.LOCAL,
        precomputed_model="voyage-4-large",
        document_embedder=HashingEmbedder(),
    )
    env = {
        **os.environ,
        "DATABASE_URL": database_url,
        "BASE_LEGAL_QUERY_EMBEDDER": "test-hashing",
        "ANTHROPIC_API_KEY": "",
    }
    params = StdioServerParameters(command=sys.executable, args=["-c", GUARD], env=env)

    async def go() -> tuple[Any, Any, Any]:
        async with Client(params) as client:
            tools = await client.list_tools()
            found = await client.call_tool("search_provisions", {"question": "art. 7º, IX"})
            check = await client.call_tool(
                "verify_citation",
                {"provision_id": "lgpd:art7:incIX", "quote": "interesses legítimos do controlador"},
            )
            return tools, found, check

    tools, found, check = anyio.run(go)
    assert {t.name for t in tools.tools} == {
        "search_provisions",
        "get_provision",
        "get_provision_history",
        "verify_citation",
    }
    assert not found.is_error
    assert found.structured_content["hits"][0]["provision"]["id"] == "lgpd:art7:incIX"
    assert check.structured_content["valid"] is True
