"""Normative change watcher: compare freshly parsed sources with the committed corpus.

Official pages change bytes without changing the law (Planalto returns
different bytes for identical content), so the comparison is made on the
parsed provisions, never on the raw hash. Only a real change to a
provision's normative content (text, label, hierarchy, revocation, veto or
amendment notes) counts; ordinals shifting because a provision was inserted
do not.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from base_legal.corpus.models import Document, Provision

MAX_QUOTE = 600


class ChangeKind(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"


@dataclass(frozen=True, slots=True)
class ProvisionChange:
    provision_id: str
    kind: ChangeKind
    before: str | None
    after: str | None


@dataclass(frozen=True, slots=True)
class DocumentDiff:
    document_id: str
    changes: tuple[ProvisionChange, ...]

    @property
    def changed(self) -> bool:
        return bool(self.changes)


def _content(provision: Provision) -> tuple[object, ...]:
    return (
        provision.text,
        provision.label,
        provision.kind,
        provision.parent_id,
        provision.path,
        provision.revoked,
        provision.vetoed,
        provision.amendments,
    )


def _describe(provision: Provision) -> str:
    if provision.revoked:
        return f"(revogado) {provision.text}".strip()
    if provision.vetoed:
        return "(VETADO)"
    return provision.text


def diff_documents(old: Document | None, new: Document) -> DocumentDiff:
    """Provision-level differences between the committed and the freshly parsed act."""
    before = old.by_id() if old is not None else {}
    after = new.by_id()
    changes: list[ProvisionChange] = []
    for provision in new.provisions:  # document order
        previous = before.get(provision.id)
        if previous is None:
            changes.append(
                ProvisionChange(provision.id, ChangeKind.ADDED, None, _describe(provision))
            )
        elif _content(previous) != _content(provision):
            changes.append(
                ProvisionChange(
                    provision.id, ChangeKind.CHANGED, _describe(previous), _describe(provision)
                )
            )
    for provision in old.provisions if old is not None else ():
        if provision.id not in after:
            changes.append(
                ProvisionChange(provision.id, ChangeKind.REMOVED, _describe(provision), None)
            )
    return DocumentDiff(new.id, tuple(changes))


def _quote(text: str | None) -> list[str]:
    """Untrusted source text, fenced so the PR body renders it as plain text."""
    if text is None:
        return ["_(none)_"]
    text = text.replace("~~~", "~ ~ ~")
    if len(text) > MAX_QUOTE:
        text = text[:MAX_QUOTE] + " […]"
    return ["~~~text", text, "~~~"]


def render_report(diffs: list[DocumentDiff], checked: list[str], date: str) -> str:
    """Markdown for the pull request a scheduled run opens when the law changed."""
    changed = [d for d in diffs if d.changed]
    lines = [
        f"# Corpus watch: {date}",
        "",
        f"Checked: {', '.join(checked)}. Acts with normative changes: "
        f"{', '.join(d.document_id for d in changed) or 'none'}.",
        "",
        "Review every change against the official page before merging, then run the",
        "evals and check whether golden items or TODO(verify) notes are affected.",
        "Text below comes from the official source and is untrusted data.",
    ]
    for diff in changed:
        lines += ["", f"## {diff.document_id} ({len(diff.changes)} provision(s))"]
        for change in diff.changes:
            lines += ["", f"### `{change.provision_id}`: {change.kind.value}"]
            if change.kind is not ChangeKind.ADDED:
                lines += ["", "Before:", "", *_quote(change.before)]
            if change.kind is not ChangeKind.REMOVED:
                lines += ["", "After:", "", *_quote(change.after)]
    return "\n".join(lines) + "\n"
