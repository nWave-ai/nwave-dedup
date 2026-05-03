"""Tree-sitter language registry — maps file extensions to grammars.

Uses ``tree-sitter-language-pack`` for batteries-included grammar loading.
Add entries here to extend coverage; the rest of the scanner is
language-agnostic by design.
"""

from __future__ import annotations

# (extension → tree-sitter grammar name) for the v0.1 covered set.
# tree-sitter-language-pack provides 100+ grammars; we whitelist the ones
# we have explicit query coverage for. Unknown extensions are skipped.
EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".rs": "rust",
    ".go": "go",
    ".rb": "ruby",
    ".ml": "ocaml",
    ".mli": "ocaml_interface",
}

# Languages where we have a query for "function-like nodes" — used by the
# scanner to extract candidate units for normalization. Adding a language
# requires (a) its grammar in tree-sitter-language-pack and (b) an entry
# in FUNCTION_NODE_TYPES below.
SUPPORTED_LANGUAGES: frozenset[str] = frozenset(EXTENSION_TO_LANGUAGE.values())

# Tree-sitter node types that count as "function-level units" per language.
# Must be aligned with the grammar's published node names; see
# https://github.com/tree-sitter/<grammar>/blob/master/src/node-types.json
FUNCTION_NODE_TYPES: dict[str, tuple[str, ...]] = {
    "python": ("function_definition", "async_function_definition"),
    "javascript": (
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
    ),
    "typescript": (
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
    ),
    "tsx": (
        "function_declaration",
        "function_expression",
        "arrow_function",
        "method_definition",
    ),
    "rust": ("function_item",),
    "go": ("function_declaration", "method_declaration"),
    "ruby": ("method", "singleton_method"),
    "ocaml": ("let_binding",),
    "ocaml_interface": ("value_specification",),
}


def language_for_path(path_suffix: str) -> str | None:
    """Return the tree-sitter grammar name for a file suffix, or None."""
    return EXTENSION_TO_LANGUAGE.get(path_suffix.lower())
