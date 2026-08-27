"""Safe repairs for text damaged by a UTF-8/legacy-encoding round trip."""

from __future__ import annotations


_MOJIBAKE_MARKERS = ("Ð", "Ñ", "Â", "Ã", "â€", "ï»¿")


def _badness(value: str) -> int:
    """Return a small heuristic score for common UTF-8 mojibake markers."""
    marker_count = sum(value.count(marker) for marker in _MOJIBAKE_MARKERS)
    control_count = sum(1 for char in value if 0x80 <= ord(char) <= 0x9F)
    return marker_count * 3 + control_count * 4 + value.count("�") * 8


def repair_utf8_mojibake(value: str | None) -> str | None:
    """Repair strings such as ``ÐÐÐ©ÐÐ¡Ð¢ÐÐ`` without touching normal text.

    Some PDF/text pipelines expose UTF-8 bytes as Latin-1 characters.  The
    reverse conversion is only accepted when it strictly reduces the number
    of well-known corruption markers, so ordinary Russian and Latin text is
    returned unchanged.
    """
    if value is None or not any(marker in value for marker in _MOJIBAKE_MARKERS):
        return value

    current = value
    # A value may have crossed the broken boundary more than once
    # (``ÃÂ...`` -> ``Ð...`` -> ``О...``).  Three passes cover that case
    # without accepting a conversion that makes the string worse.
    for _ in range(3):
        candidates = [current]
        for encoding in ("latin-1", "cp1251"):
            try:
                candidates.append(current.encode(encoding).decode("utf-8"))
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
        best = min(candidates, key=_badness)
        if _badness(best) >= _badness(current):
            break
        current = best
    return current
