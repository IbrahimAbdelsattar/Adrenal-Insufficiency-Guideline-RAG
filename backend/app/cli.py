"""Command-line interface (contracts/cli-contract.md).

    python -m backend.app.cli ingest [--dry-run] [--doc-id ID] [--verbose]
"""

from __future__ import annotations

import argparse
import sys

from backend.app.config import get_settings
from backend.app.errors import PipelineError


def _echo(message: str) -> None:
    print(message, flush=True)


# ----------------------------------------------------------------------
# ingest
# ----------------------------------------------------------------------


def cmd_ingest(args: argparse.Namespace) -> int:
    from backend.app.ingestion.pipeline import run_ingest

    settings = get_settings()
    report = run_ingest(
        settings=settings,
        doc_id=args.doc_id,
        dry_run=args.dry_run,
        report=_echo,
    )

    _echo("")
    mode = "analysed (dry run)" if report.dry_run else "indexed"
    _echo(
        f"OK  {len(report.documents)} document(s), {report.chunk_count} chunks "
        f"{mode} in {report.elapsed_seconds:.1f}s"
    )
    if report.oversized_count:
        _echo(
            f"    note: {report.oversized_count} oversized chunk(s) emitted whole "
            "and flagged (never truncated)"
        )
    return 0


# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.app.cli",
        description="Clinical Decision Support Lite — ingestion and retrieval.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    ingest = sub.add_parser("ingest", help="Rebuild the vector index from the corpus.")
    ingest.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse, clean and chunk only. No embeddings, no API cost, index untouched.",
    )
    ingest.add_argument("--doc-id", default=None, help="Restrict to one document.")
    ingest.add_argument("--verbose", action="store_true", help="Per-stage diagnostics.")
    ingest.set_defaults(func=cmd_ingest)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except PipelineError as exc:
        print(f"\nERROR: {exc}", file=sys.stderr)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
