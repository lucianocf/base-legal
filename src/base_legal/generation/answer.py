"""Grounded answers: redact, retrieve, generate with Citations, validate, or refuse.

Pipeline (ARCHITECTURE §3, ADR 0005, ADR 0011):

1. PII redaction runs first; only the redacted question goes anywhere else.
2. Retrieval (local embeddings). A nonexistent explicit reference or a best
   score below the threshold refuses *before* any model call.
3. Claude answers from the retrieved provisions with native Citations.
4. Every citation is mapped to its canonical ID and re-validated by
   :func:`base_legal.grounding.validator.judge`. Anything not grounded is
   replaced by a refusal plus the nearest provisions (text only).

Nothing here logs question or answer text; logs carry sizes, counts and
timings only (docs/PRIVACY.md).
"""

from __future__ import annotations

import logging
import time
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

from base_legal.corpus.models import Provision
from base_legal.generation.prompt import NO_SUPPORT, build_messages, system_blocks
from base_legal.grounding.validator import AnswerBlock, Citation, judge
from base_legal.privacy.redact import redact
from base_legal.retrieval.search import SearchResult

log = logging.getLogger(__name__)

DISCLAIMER = (
    "O Base Legal é uma ferramenta de pesquisa e não constitui aconselhamento jurídico. "
    "Confira sempre o texto oficial dos dispositivos citados."
)


class Status(StrEnum):
    ANSWERED = "answered"
    REFUSED = "refused"


class RefusalCause(StrEnum):
    NONEXISTENT_PROVISION = "nonexistent_provision"  # "art. 99 da LGPD"
    LOW_SCORE = "low_score"  # retrieval found nothing close enough
    MODEL_NO_SUPPORT = "model_no_support"  # the model said the documents do not answer
    UNGROUNDED = "ungrounded"  # the validator rejected the answer
    MODEL_REFUSAL = "model_refusal"  # stop_reason == "refusal"
    TRUNCATED = "truncated"  # stop_reason == "max_tokens"


REFUSAL_MESSAGES = {
    RefusalCause.NONEXISTENT_PROVISION: "O dispositivo citado não existe no corpus.",
    RefusalCause.LOW_SCORE: "Nenhum dispositivo do corpus trata do assunto.",
    RefusalCause.MODEL_NO_SUPPORT: "Os dispositivos encontrados não respondem à pergunta.",
    RefusalCause.UNGROUNDED: "A resposta gerada não pôde ser verificada no corpus.",
    RefusalCause.MODEL_REFUSAL: "O modelo recusou a pergunta.",
    RefusalCause.TRUNCATED: "A resposta excedeu o limite de tamanho.",
}


class ProvisionView(BaseModel):
    """A provision as shown to the user (always the official text, never generated)."""

    model_config = ConfigDict(frozen=True)

    id: str
    path: str
    text: str

    @classmethod
    def of(cls, provision: Provision) -> ProvisionView:
        return cls(id=provision.id, path=" > ".join(provision.path), text=provision.text)


class CitedQuote(BaseModel):
    model_config = ConfigDict(frozen=True)

    provision_id: str
    quote: str


class AnswerPart(BaseModel):
    model_config = ConfigDict(frozen=True)

    text: str
    citations: tuple[CitedQuote, ...] = ()


class Usage(BaseModel):
    model_config = ConfigDict(frozen=True)

    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0


class Answer(BaseModel):
    model_config = ConfigDict(frozen=True)

    status: Status
    parts: tuple[AnswerPart, ...] = ()
    refusal: RefusalCause | None = None
    message: str | None = None  # user-facing refusal message (PT-BR)
    refusal_details: tuple[str, ...] = ()
    provisions: tuple[ProvisionView, ...] = ()  # cited ones if answered, nearest if refused
    missing_references: tuple[str, ...] = ()
    redactions: dict[str, int] = {}
    model: str | None = None
    usage: Usage | None = None
    disclaimer: str = DISCLAIMER


class Searcher(Protocol):
    def search(self, question: str, k: int = 8) -> SearchResult: ...


class AncestorSource(Protocol):
    def provisions(self, ids: list[str]) -> dict[str, Provision]: ...


class ClaudeClient(Protocol):
    """The part of ``anthropic.Anthropic`` used here (tests pass a fake)."""

    # Any: ``anthropic.resources.Messages``, whose overloaded, keyword-only
    # ``create`` cannot be matched by a small structural protocol.
    @property
    def messages(self) -> Any: ...


class Answerer:
    def __init__(
        self,
        searcher: Searcher,
        store: AncestorSource,
        client: ClaudeClient,
        *,
        model: str,
        max_tokens: int,
        k: int = 8,
        threshold: float | None = None,
    ) -> None:
        self.searcher = searcher
        self.store = store
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.k = k
        self.threshold = threshold

    def answer(self, question: str) -> Answer:
        started = time.perf_counter()
        redacted = redact(question)  # before anything else sees the question
        result = self.searcher.search(redacted.text, k=self.k)
        provisions = [h.provision for h in result.hits]
        context = _Context(redacted.counts, result.missing_references, started)

        early = result.refusal(self.threshold)
        if early is not None or not provisions:
            cause = RefusalCause(early.value) if early else RefusalCause.LOW_SCORE
            return self._refuse(cause, provisions, context)

        response = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_blocks(),
            messages=build_messages(redacted.text, provisions, self._ancestors(provisions)),
        )
        context.model, context.usage = self.model, _usage(response)
        if response.stop_reason == "refusal":
            return self._refuse(RefusalCause.MODEL_REFUSAL, provisions, context)
        if response.stop_reason == "max_tokens":
            return self._refuse(RefusalCause.TRUNCATED, provisions, context)

        parts = _parts(response.content, provisions)
        if "".join(p.text for p in parts).strip() == NO_SUPPORT:
            return self._refuse(RefusalCause.MODEL_NO_SUPPORT, provisions, context)

        corpus = {p.id: p for p in provisions}
        verdict = judge(
            [
                AnswerBlock(p.text, tuple(Citation(c.provision_id, c.quote) for c in p.citations))
                for p in parts
            ],
            corpus,
        )
        if not verdict.grounded:
            return self._refuse(RefusalCause.UNGROUNDED, provisions, context, verdict.reasons)

        cited = list(dict.fromkeys(c.provision_id for p in parts for c in p.citations))
        log.info(
            "answered", extra={"parts": len(parts), "citations": len(cited), **context.log_fields()}
        )
        return Answer(
            status=Status.ANSWERED,
            parts=tuple(parts),
            provisions=tuple(ProvisionView.of(corpus[pid]) for pid in cited),
            redactions=context.redactions,
            missing_references=context.missing_references,
            model=context.model,
            usage=context.usage,
        )

    def _ancestors(self, provisions: Sequence[Provision]) -> dict[str, list[Provision]]:
        wanted = {
            ancestor for p in provisions for ancestor in _ancestor_ids(p.id) if ancestor != p.id
        }
        known = self.store.provisions(sorted(wanted))
        return {
            p.id: [known[a] for a in _ancestor_ids(p.id) if a != p.id and a in known]
            for p in provisions
        }

    def _refuse(
        self,
        cause: RefusalCause,
        provisions: Sequence[Provision],
        context: _Context,
        details: Sequence[str] = (),
    ) -> Answer:
        log.info("refused", extra={"cause": cause.value, **context.log_fields()})
        return Answer(
            status=Status.REFUSED,
            refusal=cause,
            message=REFUSAL_MESSAGES[cause],
            refusal_details=tuple(details),
            provisions=tuple(ProvisionView.of(p) for p in provisions[:3]),
            redactions=context.redactions,
            missing_references=context.missing_references,
            model=context.model,
            usage=context.usage,
        )


def _ancestor_ids(provision_id: str) -> list[str]:
    """``lgpd:art11:incII:alig`` -> ``[lgpd:art11, lgpd:art11:incII, …]`` (outermost first)."""
    head, *segments = provision_id.split(":")
    ids: list[str] = []
    current = head
    for segment in segments:
        current = f"{current}:{segment}"
        if not segment.startswith("anx"):
            ids.append(current)
    return ids


def _parts(content: Sequence[Any], provisions: Sequence[Provision]) -> list[AnswerPart]:
    """Text blocks with their citations mapped to canonical IDs via ``document_index``."""
    parts: list[AnswerPart] = []
    for block in content:
        if getattr(block, "type", None) != "text":
            continue
        quotes: list[CitedQuote] = []
        for citation in getattr(block, "citations", None) or ():
            index = getattr(citation, "document_index", None)
            if getattr(citation, "type", None) != "content_block_location" or not (
                isinstance(index, int) and 0 <= index < len(provisions)
            ):
                # An unmappable citation becomes an unknown ID the validator rejects.
                quotes.append(CitedQuote(provision_id="unknown:art0", quote=str(citation)))
                continue
            quotes.append(
                CitedQuote(provision_id=provisions[index].id, quote=str(citation.cited_text))
            )
        parts.append(AnswerPart(text=str(block.text), citations=tuple(quotes)))
    return parts


def _usage(response: Any) -> Usage | None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return None
    return Usage(
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_read_input_tokens=getattr(usage, "cache_read_input_tokens", None) or 0,
        cache_creation_input_tokens=getattr(usage, "cache_creation_input_tokens", None) or 0,
    )


@dataclass
class _Context:
    redactions: dict[str, int]
    missing_references: tuple[str, ...]
    started: float
    model: str | None = None
    usage: Usage | None = None

    def log_fields(self) -> dict[str, Any]:
        """Content-free: counts, sizes and timings only (docs/PRIVACY.md)."""
        fields: dict[str, Any] = {
            "elapsed_ms": round((time.perf_counter() - self.started) * 1000),
            "redactions": sum(self.redactions.values()),
        }
        if self.usage is not None:
            fields |= self.usage.model_dump()
        return fields
