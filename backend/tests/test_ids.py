"""uuid7 must be strictly monotonic — order_by(id) == insertion order (v1.0.4 fix)."""

from __future__ import annotations

from app.ids import uuid7


def test_uuid7_strictly_increasing_burst() -> None:
    # 5_000 ids minted back-to-back — mostly inside the same millisecond.
    # Before the monotonic counter these sorted *randomly*, which shuffled the
    # display order of a journal entry's splits (test_journal_lifecycle flake).
    ids = [uuid7() for _ in range(5_000)]
    assert len(set(ids)) == len(ids)
    assert ids == sorted(ids)


def test_uuid7_version_and_variant_bits() -> None:
    for raw in (uuid7(), uuid7()):
        u = raw.replace("-", "")
        assert u[12] == "7"  # version 7
        assert u[16] in "89ab"  # variant 10xx
