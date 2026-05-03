"""nwave-dedup CLI entry point.

Subcommands:
  scan       Scan one or more roots for duplicate-shape function units
  baseline   Snapshot current count, store as baseline (planned, not yet shipped)
  fix        Apply suggested refactor (planned, not yet shipped)

This is the v0.1.0.dev0 surface. Public CLI may evolve before v0.1.0 stable.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from nwave_dedup import __version__
from nwave_dedup.scanner import DuplicateGroup, scan_paths


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="nwave-dedup",
        description="Cross-language duplicate-shape scanner. Tree-sitter based.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"nwave-dedup {__version__}",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    scan = subparsers.add_parser(
        "scan", help="Scan paths for duplicate-shape function units"
    )
    scan.add_argument("paths", nargs="+", type=Path, help="One or more roots to scan")
    scan.add_argument(
        "--min-statements",
        type=int,
        default=6,
        help="Minimum statement count per unit (default: 6)",
    )
    scan.add_argument(
        "--format",
        choices=("markdown", "json"),
        default="markdown",
        help="Output format (default: markdown)",
    )
    scan.add_argument(
        "--output", type=Path, default=None, help="Write to file instead of stdout"
    )
    scan.add_argument(
        "--top", type=int, default=20, help="Show only top N groups (default: 20)"
    )

    return parser


def _render_markdown(groups: list[DuplicateGroup], top: int) -> str:
    if not groups:
        return "# Duplicate-shape scan\n\nNo duplicate groups found.\n"
    lines = [
        "# Duplicate-shape scan",
        "",
        f"**Total groups**: {len(groups)}  |  **Showing top**: {min(top, len(groups))}",
        "",
        "Groups are ordered by ROI (size DESC, statement count DESC). Each group "
        "shares an identical normalized syntax tree (identifier and literal values "
        "stripped). False-positive rate depends on language; the classifier "
        "(coming in v0.2) refines per group.",
        "",
    ]
    for i, group in enumerate(groups[:top], 1):
        lines.append(
            f"## Group {i} — {group.size} clones, ~{group.stmt_count} stmts each"
        )
        lines.append("")
        for member in group.members:
            lines.append(
                f"- `{member.path}:{member.line}` `def {member.name}()` "
                f"({member.language})"
            )
        lines.append("")
    return "\n".join(lines) + "\n"


def _render_json(groups: list[DuplicateGroup], top: int) -> str:
    payload = {
        "version": __version__,
        "total_groups": len(groups),
        "groups": [
            {
                "hash": g.hash,
                "size": g.size,
                "statement_count": g.stmt_count,
                "members": [
                    {
                        "path": str(m.path),
                        "line": m.line,
                        "end_line": m.end_line,
                        "name": m.name,
                        "language": m.language,
                    }
                    for m in g.members
                ],
            }
            for g in groups[:top]
        ],
    }
    return json.dumps(payload, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command != "scan":
        # baseline + fix are stubs; surface this honestly instead of crashing
        print(
            f"ERROR: subcommand '{args.command}' is not yet implemented (v0.1.0.dev0)",
            file=sys.stderr,
        )
        return 2

    roots = [p.resolve() for p in args.paths]
    for r in roots:
        if not r.exists():
            print(f"ERROR: path does not exist: {r}", file=sys.stderr)
            return 2

    groups = scan_paths(roots, min_statements=args.min_statements)
    if args.format == "json":
        report = _render_json(groups, args.top)
    else:
        report = _render_markdown(groups, args.top)

    if args.output:
        args.output.write_text(report, encoding="utf-8")
    else:
        sys.stdout.write(report)

    return 0


if __name__ == "__main__":
    sys.exit(main())
