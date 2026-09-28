import datetime as dt

from base_legal.corpus.models import Document, DocumentKind, Provision, ProvisionKind
from base_legal.corpus.watch import ChangeKind, diff_documents, render_report


def _provision(pid: str, text: str, ordinal: int, **extra: object) -> Provision:
    return Provision.model_validate(
        {
            "id": pid,
            "document_id": "lgpd",
            "parent_id": None,
            "kind": ProvisionKind.ARTICLE,
            "label": pid.rsplit(":", 1)[1],
            "text": text,
            "path": (pid,),
            "ordinal": ordinal,
            **extra,
        }
    )


def _document(*provisions: Provision) -> Document:
    return Document(
        id="lgpd",
        title="LGPD",
        kind=DocumentKind.LAW,
        source_url="https://example.org",
        source_sha256="a" * 64,
        retrieved_at=dt.date(2026, 9, 27),
        redistribution_basis="test",
        provisions=provisions,
    )


def test_identical_content_is_no_change_even_if_ordinals_shift() -> None:
    old = _document(_provision("lgpd:art1", "Um.", 0), _provision("lgpd:art2", "Dois.", 1))
    new = _document(_provision("lgpd:art1", "Um.", 5), _provision("lgpd:art2", "Dois.", 6))
    assert not diff_documents(old, new).changed


def test_added_removed_changed_and_revoked() -> None:
    old = _document(
        _provision("lgpd:art1", "Um.", 0),
        _provision("lgpd:art2", "Dois.", 1),
        _provision("lgpd:art3", "Três.", 2),
    )
    new = _document(
        _provision("lgpd:art1", "Um, com nova redação.", 0),
        _provision("lgpd:art2", "Dois.", 1, revoked=True),
        _provision("lgpd:art4", "Quatro.", 2),
    )
    changes = {c.provision_id: c for c in diff_documents(old, new).changes}
    assert changes["lgpd:art1"].kind is ChangeKind.CHANGED
    assert changes["lgpd:art1"].after == "Um, com nova redação."
    assert changes["lgpd:art2"].after == "(revogado) Dois."
    assert changes["lgpd:art3"].kind is ChangeKind.REMOVED
    assert changes["lgpd:art4"].kind is ChangeKind.ADDED
    assert diff_documents(None, new).changes[0].kind is ChangeKind.ADDED


def test_report_fences_untrusted_text() -> None:
    old = _document(_provision("lgpd:art1", "Um.", 0))
    hostile = "~~~\n[clique aqui](https://example.org) " + "x" * 700
    new = _document(_provision("lgpd:art1", hostile, 0))
    report = render_report([diff_documents(old, new)], ["lgpd", "lai"], "2026-09-27")
    assert "Checked: lgpd, lai. Acts with normative changes: lgpd." in report
    # the source cannot close the fence, and long text is cut
    assert report.count("~~~") == 4
    assert "[…]" in report
