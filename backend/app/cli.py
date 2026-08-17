"""Command-line interface (contracts/cli-contract.md).

    python -m backend.app.cli ingest [--dry-run] [--doc-id ID] [--verbose]
    python -m backend.app.cli query "..." [--top-k 5] [--json] [--full-text]
    python -m backend.app.cli eval [--top-k 5] [--json]
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
# query
# ----------------------------------------------------------------------


def cmd_query(args: argparse.Namespace) -> int:
    import json

    from backend.app.models import DISCLAIMER, SearchResponse
    from backend.app.retrieval.factory import get_retriever
    from backend.app.retrieval.store import VectorStore

    settings = get_settings()
    store = VectorStore(settings)
    if not store.is_ready():
        _echo("No evidence is available: the index is empty.")
        _echo("Run: python -m backend.app.cli ingest")
        return 0

    top_k = args.top_k or settings.top_k
    results = get_retriever(settings).search(args.query, top_k)

    if args.json:
        payload = SearchResponse(
            query=args.query,
            results=results,
            result_count=len(results),
            evidence_found=any(not r.below_floor for r in results),
            embedding_model=settings.embedding_model,
            disclaimer=DISCLAIMER,
        )
        print(json.dumps(payload.model_dump(mode="json"), indent=2))
        return 0

    _echo(f"Query: {args.query}")
    _echo(
        f"Model: {settings.embedding_model} | top_k={top_k} | "
        f"floor={settings.relevance_floor:.2f}"
    )
    _echo("")

    for result in results:
        chunk = result.chunk
        flag = "   [BELOW FLOOR]" if result.below_floor else ""
        caution = "   [CAUTION: non-current source]" if chunk.requires_caution else ""
        _echo(
            f"#{result.rank}  {result.score:.3f}  {chunk.document_name[:40]}  "
            f"p.{chunk.page_number}  {chunk.section_title[:48]}{flag}{caution}"
        )
        if chunk.subsection_title:
            rec = f"  [rec {chunk.recommendation_ids}]" if chunk.recommendation_ids else ""
            _echo(f"    > {chunk.subsection_title}{rec}")
        body = chunk.text if args.full_text else chunk.text[:220].replace("\n", " ")
        _echo(f"    {body}")
        _echo("")

    above = sum(1 for r in results if not r.below_floor)
    _echo(f"evidence_found: {str(bool(above)).lower()}   ({above} of {len(results)} above floor)")
    return 0


# ----------------------------------------------------------------------
# eval
# ----------------------------------------------------------------------


def cmd_eval(args: argparse.Namespace) -> int:
    import json

    from backend.app.evaluation import TARGET_HIT_RATE, evaluate
    from backend.app.retrieval.factory import get_retriever
    from backend.app.retrieval.store import VectorStore

    settings = get_settings()
    store = VectorStore(settings)
    if not store.is_ready():
        _echo("No index built. Run: python -m backend.app.cli ingest")
        return 1

    top_k = args.top_k or settings.top_k
    report = evaluate(
        get_retriever(settings),
        top_k=top_k,
        settings=settings,
    )

    if args.json:
        print(
            json.dumps(
                {
                    "top_k": report.top_k,
                    "total": report.total,
                    "hits": report.hits,
                    "hit_rate": round(report.hit_rate, 4),
                    "mean_hit_rank": round(report.mean_hit_rank, 2),
                    "target": TARGET_HIT_RATE,
                    "passed": report.passed,
                    "questions": [
                        {
                            "id": o.question.id,
                            "status": o.status,
                            "rank": o.rank,
                            "expected_sections": o.question.expected_sections,
                            "retrieved_sections": o.retrieved_sections,
                        }
                        for o in report.outcomes
                    ],
                },
                indent=2,
            )
        )
        return 0 if report.passed else 1

    _echo(f"Golden set: {report.total} questions | top_k={report.top_k}")
    _echo("")
    for outcome in report.outcomes:
        rank = f"rank {outcome.rank}" if outcome.rank else "--"
        _echo(
            f"  {outcome.question.id}  {outcome.status:<4}  {rank:<8}"
            f"expected {','.join(outcome.question.expected_sections):<9}"
            f"{outcome.question.question[:46]}"
        )

    _echo("")
    _echo(
        f"Hit rate: {report.hits}/{report.total} ({report.hit_rate:.1%})   "
        f"target >= {TARGET_HIT_RATE:.0%}   "
        f"{'PASS' if report.passed else 'FAIL'}"
    )
    if report.hits:
        _echo(f"Mean rank of hits: {report.mean_hit_rank:.1f}")
    if report.misses:
        _echo("")
        _echo("Misses (retrieved sections shown for diagnosis):")
        for outcome in report.misses:
            _echo(
                f"  {outcome.question.id}  expected "
                f"{','.join(outcome.question.expected_sections)}  "
                f"got {','.join(outcome.retrieved_sections)}"
            )

    return 0 if report.passed else 1


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

    query = sub.add_parser("query", help="Retrieve chunks for a clinical question.")
    query.add_argument("query", help="The clinical question.")
    query.add_argument("--top-k", type=int, default=0, help="Results to return.")
    query.add_argument("--json", action="store_true", help="Emit SearchResponse JSON.")
    query.add_argument(
        "--full-text", action="store_true", help="Print whole chunks, not excerpts."
    )
    query.set_defaults(func=cmd_query)

    evaluate_cmd = sub.add_parser(
        "eval", help="Run the golden question set and report retrieval hit rate."
    )
    evaluate_cmd.add_argument("--top-k", type=int, default=0, help="Retrieval depth.")
    evaluate_cmd.add_argument("--json", action="store_true", help="Emit JSON.")
    evaluate_cmd.set_defaults(func=cmd_eval)

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
