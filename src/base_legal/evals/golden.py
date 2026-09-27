"""Golden set (``evals/golden.yaml``): synthetic questions with expected provisions."""

from __future__ import annotations

from collections.abc import Collection
from enum import StrEnum
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator

from base_legal.corpus.ids import is_valid_id


class Split(StrEnum):
    DEV = "dev"  # may be used to tune retrieval
    HOLDOUT = "holdout"  # only used to confirm a change
    ALL = "all"


class RefuseReason(StrEnum):
    OUT_OF_CORPUS = "out_of_corpus"
    NONEXISTENT_PROVISION = "nonexistent_provision"
    OFF_TOPIC = "off_topic"


class _Item(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: str
    question: str = Field(min_length=1)
    split: Literal[Split.DEV, Split.HOLDOUT]
    status: Literal["unverified", "verified"]
    notes: str | None = None


class AnswerableItem(_Item):
    expected: tuple[str, ...] = Field(min_length=1)

    @field_validator("expected")
    @classmethod
    def _check_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        bad = [pid for pid in value if not is_valid_id(pid)]
        if bad:
            raise ValueError(f"malformed provision ids: {bad}")
        return value


class RefuseItem(_Item):
    reason: RefuseReason


class GoldenSet(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: int
    answerable: tuple[AnswerableItem, ...]
    refuse: tuple[RefuseItem, ...]

    @classmethod
    def load(cls, path: Path) -> GoldenSet:
        golden = cls.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))
        ids = [i.id for i in (*golden.answerable, *golden.refuse)]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise ValueError(f"duplicate golden item ids: {duplicates}")
        return golden

    def select(self, split: Split) -> GoldenSet:
        if split is Split.ALL:
            return self
        return self.model_copy(
            update={
                "answerable": tuple(i for i in self.answerable if i.split == split),
                "refuse": tuple(i for i in self.refuse if i.split == split),
            }
        )

    def unknown_ids(self, known: Collection[str]) -> list[str]:
        """Expected IDs that do not exist in the corpus (a stale golden set)."""
        return sorted({pid for i in self.answerable for pid in i.expected if pid not in known})
