"""Smoke tests for the classifier — fixture-based, no scanner dependency.

Each test exercises one classification rule with a hand-built DuplicateGroup.
"""

from __future__ import annotations

from pathlib import Path

from nwave_dedup.classifier import Classification, classify
from nwave_dedup.scanner import CandidateUnit, DuplicateGroup


def _unit(path: str, name: str = "foo", lineno: int = 10) -> CandidateUnit:
    return CandidateUnit(
        path=Path(path),
        line=lineno,
        end_line=lineno + 5,
        name=name,
        language="python",
        statement_count=10,
        normalized_hash="abc123",
    )


def test_generic_init_is_unverifiable() -> None:
    """Two classes with __init__ same shape → UNVERIFIABLE (don't over-classify)."""
    g = DuplicateGroup(
        hash="x", members=[_unit("a/b.py", "__init__"), _unit("c/d.py", "__init__")]
    )
    result = classify(g)
    assert result.classification == Classification.UNVERIFIABLE
    assert "__init__" in result.reason


def test_adapter_pattern_by_function_suffix() -> None:
    """Names ending in _uv / _pipx → ADAPTER_PATTERN."""
    g = DuplicateGroup(
        hash="x",
        members=[_unit("a/x.py", "run_uv"), _unit("b/x.py", "run_pipx")],
    )
    result = classify(g)
    assert result.classification == Classification.ADAPTER_PATTERN


def test_adapter_pattern_by_sibling_layout(tmp_path: Path) -> None:
    """Sibling files *_adapter.py in same dir → ADAPTER_PATTERN."""
    d = tmp_path / "adapters"
    d.mkdir()
    (d / "uv_adapter.py").write_text("# stub")
    (d / "pipx_adapter.py").write_text("# stub")
    g = DuplicateGroup(
        hash="x",
        members=[
            _unit(str(d / "uv_adapter.py"), "install"),
            _unit(str(d / "pipx_adapter.py"), "install"),
        ],
    )
    result = classify(g)
    assert result.classification == Classification.ADAPTER_PATTERN


def test_test_fixture_in_conftest(tmp_path: Path) -> None:
    """Function in conftest.py → TEST_FIXTURE."""
    (tmp_path / "conftest.py").write_text("# stub")
    (tmp_path / "test_x.py").write_text("# stub")
    DuplicateGroup(
        hash="x",
        members=[
            _unit(str(tmp_path / "conftest.py"), "test_logger"),
            _unit(str(tmp_path / "test_x.py"), "test_logger"),
        ],
    )
    # First member is in conftest.py → both paths recognized as test infra
    # (any() over the path set), and conftest match triggers TEST_FIXTURE
    # NOTE: the helper only looks at file SUFFIX/NAME. tmp_path/test_x.py
    # is NOT in tests/ root so the all_in_tests guard fails. To exercise the
    # rule properly we put both files under a tests/ subdir.
    g2_dir = tmp_path / "tests" / "unit"
    g2_dir.mkdir(parents=True)
    (g2_dir / "conftest.py").write_text("# stub")
    (g2_dir / "test_y.py").write_text("# stub")
    g2 = DuplicateGroup(
        hash="x",
        members=[
            _unit(str(g2_dir / "conftest.py"), "test_logger"),
            _unit(str(g2_dir / "test_y.py"), "test_logger"),
        ],
    )
    result = classify(g2)
    assert result.classification == Classification.TEST_FIXTURE


def test_structural_pytest_bdd_in_hyphen_dir(tmp_path: Path) -> None:
    """pytest-bdd step in path-with-hyphen dir → STRUCTURAL."""
    bdd_dir = tmp_path / "tests" / "plugins" / "plugin-architecture" / "acceptance"
    bdd_dir.mkdir(parents=True)
    test_file = bdd_dir / "test_one.py"
    test_file.write_text(
        "from pytest_bdd import given\n@given('foo')\ndef foo(): pass\n"
    )
    test_file2 = bdd_dir / "test_two.py"
    test_file2.write_text(
        "from pytest_bdd import given\n@given('foo')\ndef foo(): pass\n"
    )
    g = DuplicateGroup(
        hash="x",
        members=[
            _unit(str(test_file), "foo"),
            _unit(str(test_file2), "foo"),
        ],
    )
    result = classify(g)
    assert result.classification == Classification.STRUCTURAL
    assert "hyphen" in result.reason.lower()


def test_default_migratable() -> None:
    """No special markers → MIGRATABLE."""
    g = DuplicateGroup(
        hash="x",
        members=[
            _unit("src/feature_a.py", "process_data"),
            _unit("src/feature_b.py", "process_data"),
        ],
    )
    result = classify(g)
    assert result.classification == Classification.MIGRATABLE
