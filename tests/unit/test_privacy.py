import time

import pytest

from base_legal.privacy.redact import is_valid_cnpj, is_valid_cpf, redact

# Synthetic identifiers with valid check digits, used only as redaction fixtures.
VALID_CPF = "529.982.247-25"
VALID_CNPJ = "11.222.333/0001-81"
ALNUM_CNPJ = "12.ABC.345/01DE-35"


def test_cpf_check_digits() -> None:
    assert is_valid_cpf(VALID_CPF)
    assert is_valid_cpf("52998224725")
    assert not is_valid_cpf("111.222.333-44")
    assert not is_valid_cpf("111.111.111-11")  # repeated digits are invalid


def test_cnpj_check_digits_numeric_and_alphanumeric() -> None:
    assert is_valid_cnpj(VALID_CNPJ)
    assert is_valid_cnpj(ALNUM_CNPJ)
    assert not is_valid_cnpj("11.222.333/0001-82")
    assert not is_valid_cnpj("00.000.000/0000-00")


def test_redacts_valid_cpf_only() -> None:
    result = redact(f"Meu CPF é {VALID_CPF}; o protocolo 111.222.333-44 foi registrado?")
    assert result.text == "Meu CPF é [CPF_1]; o protocolo 111.222.333-44 foi registrado?"
    assert result.counts == {"CPF": 1}


def test_redacts_cnpj_email_and_phone() -> None:
    text = (
        f"A empresa {VALID_CNPJ} ({ALNUM_CNPJ}) respondeu a fulana.tal+lgpd@exemplo.com.br "
        "e ligou de +55 (11) 91234-5678 e (21) 3456-7890."
    )
    result = redact(text)
    assert result.text == (
        "A empresa [CNPJ_1] ([CNPJ_2]) respondeu a [EMAIL_1] e ligou de [PHONE_1] e [PHONE_2]."
    )
    assert result.counts == {"CNPJ": 2, "EMAIL": 1, "PHONE": 2}
    assert result.total == 5


@pytest.mark.parametrize(
    "text",
    [
        "O que diz o art. 7º, inciso IX, da Lei nº 13.709/2018?",
        "A multa é limitada a R$ 50.000.000,00 por infração (art. 52, II).",
        "Resolução CD/ANPD nº 15, de 24 de abril de 2024.",
        "Prazo de 15 dias, conforme o art. 19, II.",
    ],
)
def test_legal_questions_are_left_untouched(text: str) -> None:
    result = redact(text)
    assert result.text == text
    assert result.total == 0


def test_placeholders_are_numbered_per_type() -> None:
    result = redact(f"{VALID_CPF} e 52998224725")
    assert result.text == "[CPF_1] e [CPF_2]"


@pytest.mark.parametrize(
    "payload",
    ["+" * 20_000, "a+" * 10_000, "a" * 19_000 + "@", "x@" + "a." * 9_000, " +" * 10_000],
)
def test_redaction_is_fast_on_pathological_input(payload: str) -> None:
    # Regression for CodeQL py/polynomial-redos on the e-mail pattern: bounded
    # quantifiers keep redaction linear on the (hard-capped) API input.
    started = time.perf_counter()
    redact(payload)
    assert time.perf_counter() - started < 0.5


def test_email_limits_follow_rfc_5321() -> None:
    assert redact("escreva para " + "a" * 64 + "@example.com").counts == {"EMAIL": 1}
    assert redact("fale com joao.silva+lgpd@sub.example.com.br agora").text == (
        "fale com [EMAIL_1] agora"
    )
