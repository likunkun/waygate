from __future__ import annotations

import re


_ID_PREFIX_BOUNDARY = r'(?<![A-Za-z0-9_-])'
_ID_BODY = r'[A-Za-z0-9_-]+'
_PLACEHOLDER_BODIES = {'ID', 'IDS', 'X', 'XX', 'XXX', 'TBD', 'TODO', 'EXAMPLE'}

AC_ID_PATTERN = rf'{_ID_PREFIX_BOUNDARY}AC-{_ID_BODY}'
JOURNEY_ID_PATTERN = rf'{_ID_PREFIX_BOUNDARY}J-{_ID_BODY}'

_AC_ID_RE = re.compile(AC_ID_PATTERN, re.IGNORECASE)
_JOURNEY_ID_RE = re.compile(JOURNEY_ID_PATTERN, re.IGNORECASE)


def ordered_acceptance_criterion_ids_in_text(text: str) -> list[str]:
    return _ordered_ids(_AC_ID_RE, text)


def acceptance_criterion_ids_in_text(text: str) -> set[str]:
    return set(ordered_acceptance_criterion_ids_in_text(text))


def ordered_journey_ids_in_text(text: str) -> list[str]:
    return _ordered_ids(_JOURNEY_ID_RE, text)


def journey_ids_in_text(text: str) -> set[str]:
    return set(ordered_journey_ids_in_text(text))


def _ordered_ids(pattern: re.Pattern[str], text: str) -> list[str]:
    ids: list[str] = []
    seen: set[str] = set()
    for match in pattern.finditer(str(text or '')):
        value = match.group(0).upper()
        if _is_placeholder_id(value):
            continue
        if value in seen:
            continue
        seen.add(value)
        ids.append(value)
    return ids


def _is_placeholder_id(value: str) -> bool:
    _prefix, _separator, body = value.partition('-')
    return body in _PLACEHOLDER_BODIES
