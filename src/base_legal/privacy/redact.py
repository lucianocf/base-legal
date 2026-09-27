"""PII redaction applied to questions before any third-party call.

Detected: CPF and CNPJ (including the alphanumeric CNPJ format issued from
July 2026), validated by check digits to avoid redacting protocol numbers
and the like; e-mail addresses; Brazilian phone numbers.

Values are replaced by typed placeholders (``[CPF_1]``). The mapping back to
the original values is never kept: only per-type counts leave this module,
so they can be logged without content.

Known limitation: names, addresses and free-text health data are not
detected. Users are told not to include personal data (docs/PRIVACY.md).
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

_CPF_RE = re.compile(r"(?<![\w.])\d{3}\.?\d{3}\.?\d{3}-?\d{2}(?![\w-])")
_CNPJ_RE = re.compile(
    r"(?<![\w.])[0-9A-Z]{2}\.?[0-9A-Z]{3}\.?[0-9A-Z]{3}/?[0-9A-Z]{4}-?\d{2}(?![\w-])"
)
# Bounded by RFC 5321 (local part <= 64, labels <= 63): linear time on any input.
_EMAIL_RE = re.compile(
    r"(?<![\w.+-])[\w.+-]{1,64}@[A-Za-z0-9-]{1,63}(?:\.[A-Za-z0-9-]{1,63}){1,8}(?![\w-])"
)
_PHONE_RE = re.compile(r"(?<![\w+])(?:\+?55[\s-]?)?\(?[1-9]\d\)?[\s-]?9?\d{4}[\s-]?\d{4}(?![\w-])")


def _digits(value: str) -> str:
    return "".join(c for c in value if c.isalnum()).upper()


def is_valid_cpf(value: str) -> bool:
    digits = _digits(value)
    if len(digits) != 11 or not digits.isdigit() or len(set(digits)) == 1:
        return False
    numbers = [int(c) for c in digits]
    for position in (9, 10):
        total = sum(n * (position + 1 - i) for i, n in enumerate(numbers[:position]))
        if (total * 10) % 11 % 10 != numbers[position]:
            return False
    return True


def is_valid_cnpj(value: str) -> bool:
    """Numeric or alphanumeric CNPJ (each character valued as ``ord(c) - 48``)."""
    chars = _digits(value)
    if len(chars) != 14 or not chars[12:].isdigit() or len(set(chars)) == 1:
        return False
    values = [ord(c) - 48 for c in chars]
    for position, weights in ((12, "543298765432"), (13, "6543298765432")):
        total = sum(v * int(w) for v, w in zip(values[:position], weights, strict=True))
        remainder = total % 11
        check = 0 if remainder < 2 else 11 - remainder
        if check != values[position]:
            return False
    return True


@dataclass(frozen=True, slots=True)
class RedactionResult:
    text: str
    counts: dict[str, int] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return sum(self.counts.values())


def redact(text: str) -> RedactionResult:
    """Replace detected personal data with typed placeholders."""
    counts: Counter[str] = Counter()

    def substitute(
        pattern: re.Pattern[str], kind: str, valid: Callable[[str], bool] | None = None
    ) -> Callable[[re.Match[str]], str]:
        def replace(match: re.Match[str]) -> str:
            value = match.group(0)
            if valid is not None and not valid(value):
                return value
            counts[kind] += 1
            return f"[{kind}_{counts[kind]}]"

        return replace

    # Order matters: CNPJ/CPF first so their digits are not taken as phones.
    text = _CNPJ_RE.sub(substitute(_CNPJ_RE, "CNPJ", is_valid_cnpj), text)
    text = _CPF_RE.sub(substitute(_CPF_RE, "CPF", is_valid_cpf), text)
    text = _EMAIL_RE.sub(substitute(_EMAIL_RE, "EMAIL"), text)
    text = _PHONE_RE.sub(substitute(_PHONE_RE, "PHONE"), text)
    return RedactionResult(text=text, counts=dict(counts))
