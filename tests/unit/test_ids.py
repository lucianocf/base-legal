import pytest

from base_legal.corpus.ids import (
    InvalidProvisionIdError,
    ProvisionRef,
    annex_key,
    article_key,
    inciso_key,
    is_valid_id,
    paragraph_key,
    parse_id,
)


@pytest.mark.parametrize(
    "provision_id",
    [
        "lgpd:art7",
        "lgpd:art7:incIX",
        "lgpd:art11:incII:alig",
        "lgpd:art48:par1:incIII",
        "lgpd:art24:paru",
        "lgpd:art55J:incIV",
        "lgpd:art65:incI-A",
        "res-anpd-15-2024:art6",
        "res-anpd-15-2024:anx1:art6",
        "res-anpd-19-2024:anx2:art1:par1:incIV:alia",
        "lgpd:art11:incII:alia:item1",
    ],
)
def test_valid_ids_round_trip(provision_id: str) -> None:
    assert is_valid_id(provision_id)
    assert str(parse_id(provision_id)) == provision_id


@pytest.mark.parametrize(
    "provision_id",
    [
        "",
        "lgpd",
        "lgpd:art",
        "LGPD:art7",
        "lgpd:art7:inc9",
        "lgpd:art7:incix",
        "lgpd:art7:incIX:par1",  # wrong order
        "lgpd:art7:aliG",
        "lgpd:art7 ",
        "lgpd:art7:incIA",  # suffix must keep the hyphen
    ],
)
def test_invalid_ids(provision_id: str) -> None:
    assert not is_valid_id(provision_id)
    with pytest.raises(InvalidProvisionIdError):
        parse_id(provision_id)


def test_parse_components() -> None:
    assert parse_id("lgpd:art48:par1:incIII") == ProvisionRef(
        doc="lgpd", article="48", paragraph="1", inciso="III"
    )


def test_key_builders() -> None:
    assert article_key("55", "j") == "55J"
    assert article_key("07") == "7"
    assert paragraph_key(None) == "u"
    assert paragraph_key("01") == "1"
    assert inciso_key("i", "a") == "I-A"
    assert inciso_key("IX") == "IX"


@pytest.mark.parametrize(
    ("fn", "arg"), [(article_key, "7A"), (paragraph_key, "x"), (inciso_key, "9")]
)
def test_key_builders_reject_garbage(fn: object, arg: str) -> None:
    with pytest.raises(InvalidProvisionIdError):
        fn(arg)  # type: ignore[operator]


def test_annex_segment() -> None:
    ref = parse_id("res-anpd-15-2024:anx1:art6:par2")
    assert ref.annex == "1"
    assert ref.article == "6"
    assert ref.paragraph == "2"
    assert str(ProvisionRef(doc="res-anpd-4-2023", article="7", annex="1")) == (
        "res-anpd-4-2023:anx1:art7"
    )
    for bad in ("res:anx0:art1", "res:anxI:art1", "res:anx1", "res:art1:anx1"):
        assert not is_valid_id(bad), bad


@pytest.mark.parametrize(
    ("printed", "expected"),
    [(None, "1"), ("ÚNICO", "1"), ("I", "1"), ("II", "2"), ("IV", "4"), ("IX", "9"), ("XIV", "14")],
)
def test_annex_key(printed: str | None, expected: str) -> None:
    assert annex_key(printed) == expected


def test_annex_key_rejects_non_roman() -> None:
    with pytest.raises(InvalidProvisionIdError):
        annex_key("A")
