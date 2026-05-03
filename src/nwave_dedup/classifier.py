"""Classify duplicate groups by refactor disposition.

Maps each ``DuplicateGroup`` to one of:

- **MIGRATABLE** — production code, no special context. Default refactor target.
- **STRUCTURAL** — duplication required by tooling constraints (e.g. pytest-bdd
  step registration in path-with-hyphen directories that aren't Python-importable).
- **ADAPTER_PATTERN** — intentional polymorphism over a vendor / version axis
  (e.g. ``_run_X`` for X in {uv, pipx}). Refactoring would couple unrelated
  concerns.
- **TEST_FIXTURE** — test helper duplicated across conftest layers; the
  expected fix is conftest consolidation, not a shared production helper.
- **UNVERIFIABLE** — accidental shape match on a generic name (``__init__``,
  ``setUp``, ``__eq__``). Human review required; tool refuses to opine.

Earned Trust note: every classification is heuristic. False positives are
expected. The classifier outputs a verdict + the reasoning so a developer
can override it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from nwave_dedup.scanner import DuplicateGroup


class Classification(str, Enum):
    MIGRATABLE = "MIGRATABLE"
    STRUCTURAL = "STRUCTURAL"
    ADAPTER_PATTERN = "ADAPTER_PATTERN"
    TEST_FIXTURE = "TEST_FIXTURE"
    UNVERIFIABLE = "UNVERIFIABLE"


@dataclass(frozen=True)
class ClassificationResult:
    classification: Classification
    reason: str  # One-sentence explanation


# ─── Detection rules ───────────────────────────────────────────────────────

# Function names that are framework-mandated and inherently duplicate-shaped
_GENERIC_NAMES: frozenset[str] = frozenset(
    {
        "__init__",
        "__eq__",
        "__hash__",
        "__repr__",
        "__str__",
        "setUp",
        "tearDown",
        "setup",
        "teardown",
        "main",
        "<anonymous>",
    }
)

# Adapter suffix patterns — function names ending in known vendor / version axes
_ADAPTER_SUFFIX_RE = re.compile(
    r"_(uv|pipx|pip|conda|brew|apt|yum|dnf|"  # package managers
    r"v\d+|legacy|next|"  # versioning
    r"linux|macos|windows|wsl|"  # platforms
    r"http|grpc|rest|graphql|"  # protocols
    r"openai|anthropic|claude|gpt|gemini)$",  # LLM vendors
    re.IGNORECASE,
)

# Path patterns
_TEST_FIXTURE_PATH_RE = re.compile(r"(^|/)conftest\.py$|(^|/)_?test_helpers?\.py$")
_TESTS_ROOT_RE = re.compile(r"(^|/)tests?/")
_BDD_STEPS_DIR_RE = re.compile(r"/steps/")
# A path segment containing a hyphen is not a valid Python module name; pytest-bdd
# step files in such a directory cannot be imported via dotted path, forcing
# local re-declaration.
_NON_PYTHON_DIR_RE = re.compile(r"(^|/)[A-Za-z][A-Za-z0-9_]*-[A-Za-z0-9_-]+/")

# pytest-bdd decorator markers (search target — first ~5 KB of file is enough)
_PYTEST_BDD_DECORATOR_RE = re.compile(r"@(given|when|then|scenario|scenarios)\s*\(")
_PYTEST_FIXTURE_RE = re.compile(r"@pytest\.fixture")


def classify(group: DuplicateGroup) -> ClassificationResult:
    """Classify a duplicate group. Returns ``(verdict, one-line reason)``."""
    if not group.members:
        return ClassificationResult(
            Classification.UNVERIFIABLE, "Empty group (defensive)"
        )

    paths = [m.path for m in group.members]
    names = [m.name for m in group.members]
    name_set = set(names)

    # Generic-name → UNVERIFIABLE (don't over-classify)
    if name_set.issubset(_GENERIC_NAMES):
        return ClassificationResult(
            Classification.UNVERIFIABLE,
            f"Generic name(s) {sorted(name_set)} — accidental shape match likely; "
            "human review required",
        )

    # All members under tests/? → may be TEST_FIXTURE or STRUCTURAL
    all_in_tests = all(_TESTS_ROOT_RE.search(str(p)) for p in paths)

    if all_in_tests:
        # STRUCTURAL — pytest-bdd step files in path-with-hyphen dirs
        non_python_dir_paths = [p for p in paths if _NON_PYTHON_DIR_RE.search(str(p))]
        if non_python_dir_paths and _has_pytest_bdd_decorator(non_python_dir_paths[0]):
            return ClassificationResult(
                Classification.STRUCTURAL,
                "pytest-bdd step in path-with-hyphen directory "
                f"({non_python_dir_paths[0].parent.name!r}) — Python import unavailable, "
                "local re-declaration required by tooling",
            )

        # TEST_FIXTURE — at least one member in conftest.py / *_test_helpers.py
        # OR has @pytest.fixture decorator
        is_conftest_dup = any(_TEST_FIXTURE_PATH_RE.search(str(p)) for p in paths)
        is_fixture_decorated = _has_pytest_fixture(paths[0])
        if is_conftest_dup or is_fixture_decorated:
            return ClassificationResult(
                Classification.TEST_FIXTURE,
                "Test helper / fixture duplicated — fix is conftest consolidation, "
                "not a production helper extraction",
            )

        # In tests but not conftest, no fixture decorator, no BDD path constraint
        # → still TEST_FIXTURE-ish but with lower confidence; defer to MIGRATABLE
        # so the developer is prompted to consider extraction. (False-positive
        # rate is acceptable here — over-flagging is safer than under-flagging
        # in a test suite where helpers SHOULD be shared.)

    # ADAPTER_PATTERN — function name suffix matches known vendor/version axis
    suffix_matches = [n for n in names if _ADAPTER_SUFFIX_RE.search(n)]
    if suffix_matches:
        return ClassificationResult(
            Classification.ADAPTER_PATTERN,
            f"Function name suffix(es) {suffix_matches[:2]} matches a known "
            "vendor / version / platform axis — likely intentional polymorphism",
        )

    # ADAPTER_PATTERN — sibling files in a directory whose siblings differ only
    # by vendor suffix (e.g. uv_package_manager_adapter.py vs pipx_*)
    if _is_sibling_adapter_layout(paths):
        return ClassificationResult(
            Classification.ADAPTER_PATTERN,
            "Sibling files share '*_adapter.py' / '*_implementation.py' suffix "
            "convention — intentional polymorphism over a vendor/protocol axis",
        )

    # Default
    return ClassificationResult(
        Classification.MIGRATABLE,
        f"{group.size} clones × ~{group.stmt_count} stmts in production code; "
        "no structural / adapter / fixture markers detected — extract to shared helper",
    )


# ─── Heuristic helpers ─────────────────────────────────────────────────────


def _has_pytest_bdd_decorator(path: Path) -> bool:
    """Does the file contain @given/@when/@then/@scenarios decorators?"""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:5000]
    except OSError:
        return False
    return bool(_PYTEST_BDD_DECORATOR_RE.search(head))


def _has_pytest_fixture(path: Path) -> bool:
    """Does the file use @pytest.fixture decorator?"""
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:5000]
    except OSError:
        return False
    return bool(_PYTEST_FIXTURE_RE.search(head))


def _is_sibling_adapter_layout(paths: list[Path]) -> bool:
    """Are all paths sibling files matching `*_<vendor>_*_adapter.py` pattern?"""
    if len({p.parent for p in paths}) != 1:  # not all in same dir
        return False
    stems = [p.stem for p in paths]
    # Common adapter suffix in stem
    return all(
        any(stem.endswith(suf) for suf in ("_adapter", "_implementation", "_impl"))
        for stem in stems
    )
