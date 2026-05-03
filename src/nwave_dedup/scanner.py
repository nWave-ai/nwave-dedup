"""Core duplicate-shape scanner — tree-sitter normalization + grouping.

Algorithm:
1. Walk file tree, dispatch each file to its tree-sitter grammar.
2. Extract candidate units (functions, methods) per language.
3. Normalize each unit's syntax tree (strip identifiers + literal values).
4. Hash the normalized tree; group by hash.
5. Return groups with >=2 members as duplicate candidates.

Identifier-stripping is structural: two functions with the same shape but
different variable names will hash to the same value. Literal values are
collapsed to their type ("_str_", "_int_", etc.) so that constant differences
do not break grouping.

False positives are expected — the classifier (separate module) refines
the verdict per group.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from nwave_dedup.languages import (
    FUNCTION_NODE_TYPES,
    SUPPORTED_LANGUAGES,
    language_for_path,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Iterator


@dataclass(frozen=True)
class CandidateUnit:
    """A function-like syntax unit extracted from a source file."""

    path: Path
    line: int
    end_line: int
    name: str
    language: str
    statement_count: int
    normalized_hash: str


@dataclass
class DuplicateGroup:
    """Set of >=2 units that share the same normalized hash."""

    hash: str
    members: list[CandidateUnit] = field(default_factory=list)

    @property
    def size(self) -> int:
        return len(self.members)

    @property
    def stmt_count(self) -> int:
        return self.members[0].statement_count if self.members else 0


def scan_paths(
    roots: Iterable[Path],
    *,
    min_statements: int = 6,
    skip_dirs: tuple[str, ...] = (
        ".venv",
        "node_modules",
        "__pycache__",
        ".hypothesis",
        ".git",
        "dist",
        "build",
        ".pytest_cache",
    ),
) -> list[DuplicateGroup]:
    """Scan one or more roots and return duplicate groups, ordered by ROI.

    ROI ordering: (group_size desc, statement_count desc).
    """
    sigs: dict[str, list[CandidateUnit]] = defaultdict(list)
    for root in roots:
        for unit in _iter_units(
            root, min_statements=min_statements, skip_dirs=skip_dirs
        ):
            sigs[unit.normalized_hash].append(unit)

    groups = [
        DuplicateGroup(hash=h, members=members)
        for h, members in sigs.items()
        if len(members) >= 2
    ]
    groups.sort(key=lambda g: (-g.size, -g.stmt_count))
    return groups


def _iter_units(
    root: Path,
    *,
    min_statements: int,
    skip_dirs: tuple[str, ...],
) -> Iterator[CandidateUnit]:
    """Yield every candidate function-like unit under ``root``."""
    # Lazy import keeps top-level import-time cost low; tree-sitter binding
    # initialization is non-trivial.
    from tree_sitter_language_pack import get_parser

    parser_cache: dict[str, object] = {}

    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in skip_dirs for part in path.parts):
            continue
        lang = language_for_path(path.suffix)
        if lang is None or lang not in SUPPORTED_LANGUAGES:
            continue

        try:
            source = path.read_bytes()
        except OSError:
            continue

        parser = parser_cache.get(lang)
        if parser is None:
            try:
                parser = get_parser(lang)
            except Exception:
                # Grammar unavailable in installed language pack version
                continue
            parser_cache[lang] = parser

        tree = parser.parse(source)
        for unit in _extract_functions(
            tree.root_node, path, lang, source, min_statements
        ):
            yield unit


def _extract_functions(
    root_node: object,
    path: Path,
    language: str,
    source: bytes,
    min_statements: int,
) -> Iterator[CandidateUnit]:
    """Walk the tree and emit candidate units that meet the size threshold."""
    target_types = FUNCTION_NODE_TYPES.get(language, ())
    if not target_types:
        return

    stack: list[object] = [root_node]
    while stack:
        node = stack.pop()
        node_type = node.type  # type: ignore[attr-defined]
        if node_type in target_types:
            stmt_count = _count_statements(node)
            if stmt_count >= min_statements:
                normalized = _normalize_node(node, source)
                hashed = hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]
                yield CandidateUnit(
                    path=path,
                    line=node.start_point[0] + 1,  # type: ignore[attr-defined]
                    end_line=node.end_point[0] + 1,  # type: ignore[attr-defined]
                    name=_function_name(node, source) or "<anonymous>",
                    language=language,
                    statement_count=stmt_count,
                    normalized_hash=hashed,
                )
        # Continue descending — nested functions count as separate units.
        stack.extend(reversed(node.children))  # type: ignore[attr-defined]


def _count_statements(node: object) -> int:
    """Approximate statement count: number of direct children with kind ending
    in '_statement' or being a 'block' / 'function_body' container's children.

    Tree-sitter node kind names vary per grammar; this heuristic matches
    common patterns (Python: '*_statement'; JS: '*_statement'; Rust:
    'expression_statement', 'let_declaration'). Off-by-one across grammars
    is acceptable — duplicates are still grouped consistently within the
    same grammar.
    """
    count = 0
    stack: list[object] = list(node.children)  # type: ignore[attr-defined]
    while stack:
        child = stack.pop()
        kind = child.type  # type: ignore[attr-defined]
        if kind.endswith("_statement") or kind in {
            "let_declaration",
            "expression_statement",
        }:
            count += 1
        stack.extend(child.children)  # type: ignore[attr-defined]
    return count


def _function_name(node: object, source: bytes) -> str | None:
    """Best-effort function name extraction from a function-like node."""
    for child in node.children:  # type: ignore[attr-defined]
        if child.type in {"identifier", "name", "type_identifier"}:
            return source[child.start_byte : child.end_byte].decode(
                "utf-8", errors="replace"
            )
    return None


def _normalize_node(node: object, source: bytes) -> str:
    """Render a syntax tree as a structural-only string (no identifiers, no
    literal values).

    The output is deterministic for a given grammar version. Two functions
    that differ only in variable names + literal values produce the same
    normalized string and therefore the same hash.
    """
    parts: list[str] = []
    _normalize_walk(node, source, parts)
    return "".join(parts)


def _normalize_walk(node: object, source: bytes, parts: list[str]) -> None:
    kind = node.type  # type: ignore[attr-defined]
    children = node.children  # type: ignore[attr-defined]

    if kind in {
        "identifier",
        "name",
        "type_identifier",
        "field_identifier",
        "property_identifier",
    }:
        parts.append("(_id_)")
        return
    if kind in {"string", "string_literal", "raw_string_literal"}:
        parts.append("(_str_)")
        return
    if kind in {"integer", "integer_literal", "number"}:
        parts.append("(_int_)")
        return
    if kind in {"float", "float_literal"}:
        parts.append("(_float_)")
        return
    if kind in {"true", "false", "boolean", "boolean_literal", "none", "nil", "null"}:
        parts.append("(_bool_)")
        return

    parts.append(f"({kind}")
    for child in children:
        _normalize_walk(child, source, parts)
    parts.append(")")
