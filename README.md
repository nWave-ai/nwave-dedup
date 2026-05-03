# nwave-dedup

> Cross-language code duplication scanner + classifier + fix-suggester.
> Tree-sitter based. Part of the [nWave](https://github.com/nWave-ai/nWave) ecosystem.

[![CI](https://github.com/nWave-ai/nwave-dedup/actions/workflows/ci.yml/badge.svg)](https://github.com/nWave-ai/nwave-dedup/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10+-blue)](https://github.com/nWave-ai/nwave-dedup)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## What it does

Finds **duplicate logic** across your codebase — not just byte-identical copies but
structurally similar functions. Then **classifies** what's safe to refactor and
suggests how:

| Class             | Meaning                                                          | Action                          |
|-------------------|------------------------------------------------------------------|---------------------------------|
| `MIGRATABLE`      | Production code, no special context                              | Extract to shared helper        |
| `STRUCTURAL`      | Required by tooling (e.g. pytest-bdd in `path-with-hyphen` dirs) | Document, don't refactor        |
| `ADAPTER_PATTERN` | Intentional polymorphism (`_uv` vs `_pipx`, `v1` vs `v2`)        | Document as design choice       |
| `TEST_FIXTURE`    | Test helpers duplicated across conftest layers                   | Consolidate via conftest        |
| `UNVERIFIABLE`    | Generic name (`__init__`, `setUp`) — accidental shape match      | Human review required           |

## Why it exists

Manual code review misses duplicate logic across modules. AST-based scanners
typically support only one language. nwave-dedup uses
[tree-sitter](https://tree-sitter.github.io/) to parse 50+ languages from a
single Python CLI, classifies findings honestly (no false-positive dump),
and suggests concrete refactor paths.

The **honesty bar** is the differentiator: a duplicate that *looks* like a
refactor candidate but is actually an intentional adapter pattern is worse
than no flag at all — it trains developers to ignore the tool. Every
classification carries a one-line reason a human can override.

## Install

```bash
pip install git+https://github.com/nWave-ai/nwave-dedup.git
```

## Usage

```bash
# Scan your project, get markdown report (default top 20 groups)
nwave-dedup scan src/ tests/

# JSON output (CI-friendly)
nwave-dedup scan src/ --format json --output report.json

# Tune sensitivity: only flag functions ≥10 statements
nwave-dedup scan src/ --min-statements 10

# Show all groups (not just top 20)
nwave-dedup scan src/ --top 1000
```

### Sample output

```markdown
# Duplicate-shape scan

**Total groups**: 4  |  **Showing top**: 4

**Classification summary** (heuristic — every verdict needs human confirm):

| Class           | Count |
|-----------------|-------|
| MIGRATABLE      | 1 |
| ADAPTER_PATTERN | 2 |
| TEST_FIXTURE    | 0 |
| STRUCTURAL      | 1 |
| UNVERIFIABLE    | 0 |

## Group 1 [MIGRATABLE] — 2 clones, ~12 stmts each

_2 clones × ~12 stmts in production code; no structural / adapter / fixture
markers detected — extract to shared helper_

- `src/uninstall.py:42` `def remove_agents()` (python)
- `src/uninstall.py:71` `def remove_commands()` (python)
```

## Status

**Pre-alpha** (`v0.1.0.dev0`). Currently shipped:

- Multi-language scanner: Python, JavaScript, TypeScript, Rust, Go, Ruby, OCaml
- Classifier with 5 heuristic classes (see table above)
- Markdown + JSON output formats

Planned for `v0.2`:

- `nwave-dedup baseline` — snapshot current count, fail CI if it increases
- `nwave-dedup fix --interactive` — refactor wizard for `MIGRATABLE` groups
- Expanded language support (more grammars from tree-sitter-language-pack)
- Performance: incremental scan via mtime cache

## Honest limitations

- **Classifier is heuristic, not proof.** False positives exist; every verdict
  carries a reason string a human can override. Earned Trust applies.
- **AST-shape only.** Two functions with identical structure but different
  semantics (e.g. one increments, one decrements) hash to the same group.
- **Per-grammar cost.** Each language adds ~1-3 MB to the wheel via
  `tree-sitter-language-pack`. The current pin (`0.7.0`) bundles all 50+
  languages by default — future versions may split this.

## License

MIT — see [LICENSE](LICENSE).

## Related

- [nWave](https://github.com/nWave-ai/nWave) — parent methodology framework
- [tree-sitter](https://tree-sitter.github.io/) — the multi-language parser engine
