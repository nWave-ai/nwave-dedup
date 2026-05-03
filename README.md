# nwave-dedup

> Cross-language code duplication scanner + classifier + fix-suggester.
> Tree-sitter based. Part of the [nWave](https://github.com/nWave-ai/nWave) ecosystem.

## What it does

Finds **duplicate logic** across your codebase — not just byte-identical copies but
structurally similar functions. Then **classifies** what's safe to refactor and
suggests how:

- **MIGRATABLE** — production code, eliminate via shared helper extraction
- **STRUCTURAL** — duplication required by tooling constraints (e.g. pytest-bdd
  step registration in path-with-hyphen directories); flagged but not refactored
- **ADAPTER_PATTERN** — intentional polymorphism (e.g. `uv` vs `pipx` adapters);
  documented as legitimate design
- **TEST_FIXTURE** — test helper shareable via conftest migration

## Why it exists

Manual code review misses duplicate logic across modules. AST-based scanners
typically support only one language. nwave-dedup uses [tree-sitter](https://tree-sitter.github.io/)
to parse 50+ languages from a single Python CLI, classifies findings honestly
(no false-positive dump), and suggests concrete refactor paths.

## Status

**Pre-alpha** (v0.1.0.dev0). Initial language support: Python, JavaScript,
TypeScript, Rust, Go, Ruby, OCaml. Pending: classifier heuristics, fix-suggester,
CI integration recipes.

## Install (pre-alpha)

```bash
pip install git+https://github.com/nWave-ai/nwave-dedup.git
```

## Usage (planned, not all implemented yet)

```bash
# Scan current dir
nwave-dedup scan

# Scan specific paths
nwave-dedup scan src/ tests/

# JSON output for CI integration
nwave-dedup scan --format json --output report.json

# Snapshot baseline (CI quality gate)
nwave-dedup baseline

# CI: fail if duplicate count increases vs baseline
nwave-dedup baseline --check
```

## License

MIT — see [LICENSE](LICENSE).
