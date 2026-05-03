"""Smoke tests for the scanner — fast, no real codebase dependency.

These verify the scanner produces SOMETHING reasonable on a tiny fixture.
Real-world dogfood verification (against nWave-dev) is a separate concern
and out of scope for unit tests.
"""

from __future__ import annotations

from pathlib import Path

from nwave_dedup.scanner import scan_paths


def test_scan_python_fixture_finds_two_clones(tmp_path: Path) -> None:
    """Two near-identical Python functions in fixture → grouped together."""
    src = tmp_path / "src"
    src.mkdir()

    fixture_a = src / "module_a.py"
    fixture_a.write_text(
        '''\
def foo(x):
    """Docstring A."""
    a = x + 1
    b = a * 2
    c = b - 3
    d = c / 4
    e = d % 5
    f = e + 6
    return f
''',
        encoding="utf-8",
    )
    fixture_b = src / "module_b.py"
    fixture_b.write_text(
        '''\
def bar(y):
    """Docstring B."""
    aa = y + 10
    bb = aa * 20
    cc = bb - 30
    dd = cc / 40
    ee = dd % 50
    ff = ee + 60
    return ff
''',
        encoding="utf-8",
    )

    groups = scan_paths([src], min_statements=6)

    # Both functions have the same shape (assignment chain + return).
    # They differ only in identifier names + literal values, which the
    # normalizer collapses. Expect at least one group with 2 members.
    assert any(g.size == 2 for g in groups), (
        f"Expected a 2-clone group, got: {[(g.size, [m.name for m in g.members]) for g in groups]}"
    )


def test_scan_empty_dir_returns_no_groups(tmp_path: Path) -> None:
    """No source files → no groups."""
    groups = scan_paths([tmp_path])
    assert groups == []


def test_scan_skips_unsupported_extensions(tmp_path: Path) -> None:
    """Files with unknown extensions are silently skipped (no crash)."""
    (tmp_path / "weird.xyz").write_text("not source code", encoding="utf-8")
    (tmp_path / "also_weird.123").write_text("nope", encoding="utf-8")

    groups = scan_paths([tmp_path])
    assert groups == []
