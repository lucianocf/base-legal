"""Normalized corpus data model (committed as JSON under ``corpus/``)."""

from __future__ import annotations

import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from base_legal.corpus.ids import is_valid_id, validate_doc_id


class ProvisionKind(StrEnum):
    ARTICLE = "article"
    PARAGRAPH = "paragraph"
    INCISO = "inciso"
    ALINEA = "alinea"
    ITEM = "item"


class DocumentKind(StrEnum):
    LAW = "law"
    RESOLUTION = "resolution"


class SourceLayout(StrEnum):
    """HTML layout of an official source; selects where the act's text lives."""

    PLANALTO = "planalto"  # planalto.gov.br compiled texts: the whole <body>
    DOU = "dou"  # in.gov.br (Diário Oficial da União): <div class="texto-dou">
    GOVBR = "govbr"  # gov.br portal pages: <div id="page-document">


class Provision(BaseModel):
    """One node of a legal text: an article (its caput), paragraph, inciso, alínea or item."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    document_id: str
    parent_id: str | None
    kind: ProvisionKind
    label: str = Field(description='As printed, e.g. "Art. 7º", "§ 1º", "IX", "a)"')
    text: str = Field(description="Normalized text of this node only, without children")
    path: tuple[str, ...] = Field(
        description="Hierarchy labels from the document root down to this node"
    )
    amendments: tuple[str, ...] = ()
    revoked: bool = False
    vetoed: bool = Field(default=False, description='"(VETADO)": no normative content')
    ordinal: int = Field(ge=0, description="Position in document order")
    valid_from: dt.date | None = None
    valid_to: dt.date | None = None

    @property
    def is_normative(self) -> bool:
        """In force and with content: the only provisions that may be indexed or cited."""
        return not (self.revoked or self.vetoed)

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not is_valid_id(value):
            raise ValueError(f"not a canonical provision id: {value!r}")
        return value

    @model_validator(mode="after")
    def _check_document_prefix(self) -> Provision:
        if not self.id.startswith(f"{self.document_id}:"):
            raise ValueError(f"{self.id!r} does not belong to document {self.document_id!r}")
        return self


class Document(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: str
    title: str
    kind: DocumentKind
    source_url: str
    source_sha256: str
    retrieved_at: dt.date
    redistribution_basis: str
    provisions: tuple[Provision, ...]

    @field_validator("id")
    @classmethod
    def _check_doc_id(cls, value: str) -> str:
        return validate_doc_id(value)

    @model_validator(mode="after")
    def _check_tree(self) -> Document:
        ids = [p.id for p in self.provisions]
        if len(ids) != len(set(ids)):
            dupes = sorted({i for i in ids if ids.count(i) > 1})
            raise ValueError(f"duplicate provision ids: {dupes}")
        known = set(ids)
        for provision in self.provisions:
            if provision.document_id != self.id:
                raise ValueError(f"{provision.id!r} has wrong document_id")
            if provision.parent_id is not None and provision.parent_id not in known:
                raise ValueError(f"{provision.id!r} has unknown parent {provision.parent_id!r}")
        return self

    def by_id(self) -> dict[str, Provision]:
        return {p.id: p for p in self.provisions}

    def in_force(self) -> tuple[Provision, ...]:
        return tuple(p for p in self.provisions if p.is_normative)
