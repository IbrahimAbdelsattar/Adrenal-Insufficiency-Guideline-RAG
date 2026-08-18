"""Command-line interface (contracts/cli-contract.md, Day 2 Lab).

python -m backend.app.cli ingest [--dry-run] [--doc-id ID] [--strategy {section,fixed}] [--verbose]
python -m backend.app.cli query "..." [--top-k 5] [--retriever-type {dense,bm25,hybrid,hybrid_rerank}] [--json] [--full-text]
python -m backend.app.cli eval [--top-k 5] [--retriever-type {dense,bm25,hybrid,hybrid_rerank}] [--matrix] [--json]
python -m backend.app.cli benchmark [--output FILE] [--json]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

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
    from backend.app.retrieval.scope import classify_scope
    from backend.app.retrieval.store import VectorStore

    settings = get_settings()
    store = VectorStore(settings)
    if not store.is_ready():
        _echo("No evidence is available: the index is empty.")
        _echo("Run: python -m backend.app.cli ingest")
        return 0

    top_k = args.top_k or settings.top_k
    retriever_type = args.retriever_type or settings.retriever_type
    retriever = get_retriever(retriever_type=retriever_type, store=store, settings=settings)
    results = retriever.search(args.query, top_k)

    if args.json:
        scope_status, scope_message, shown = classify_scope(results, settings.scope_threshold)
        payload = SearchResponse(
            query=args.query,
            results=shown,
            result_count=len(shown),
            evidence_found=scope_status == "in_scope",
            scope_status=scope_status,
            scope_message=scope_message,
            embedding_model=settings.embedding_model,
            disclaimer=DISCLAIMER,
        )
        print(json.dumps(payload.model_dump(mode="json"), indent=2))
        return 0

    # Apply the same guardrail the API does, so the CLI cannot answer a
    # question the served endpoints would reject as out of scope.
    scope_status, scope_message, shown = classify_scope(results, settings.scope_threshold)

    _echo(f"Query: {args.query}")
    _echo(
        f"Retriever: {retriever_type} | Model: {settings.embedding_model} | top_k={top_k} | "
        f"floor={settings.relevance_floor:.2f} | scope={settings.scope_threshold:.2f}"
    )
    _echo("")

    if scope_status == "out_of_scope":
        _echo(f"scope: {scope_status}")
        _echo(scope_message)
        return 0

    for result in shown:
        chunk = result.chunk
        flag = "   [BELOW FLOOR]" if result.below_floor else ""
        caution = "   [CAUTION: non-current source]" if chunk.requires_caution else ""
        _echo(
            f"#{result.rank}  rel={result.absolute_relevance:.3f}  {chunk.document_name[:40]}  "
            f"p.{chunk.page_number}  sec {chunk.section_number} - {chunk.section_title[:38]}{flag}{caution}"
        )
        if chunk.subsection_title:
            rec = f"  [rec {chunk.recommendation_ids}]" if chunk.recommendation_ids else ""
            _echo(f"    > {chunk.subsection_title}{rec}")
        body = chunk.text if args.full_text else chunk.text[:220].replace("\n", " ")
        _echo(f"    {body}")
        _echo("")

    above = sum(1 for r in shown if not r.below_floor)
    _echo(f"scope: {scope_status}")
    _echo(f"evidence_found: {str(bool(above)).lower()}   ({above} of {len(shown)} above floor)")
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
    retriever_type = args.retriever_type or settings.retriever_type
    retriever = get_retriever(retriever_type=retriever_type, store=store, settings=settings)

    report = evaluate(
        retriever,
        top_k=top_k,
        settings=settings,
        retriever_name=retriever_type.upper(),
        chunking_config=getattr(args, "chunking_config", "Section-Aware"),
    )

    if getattr(args, "matrix", False):
        print(report.to_markdown_matrix())
        return 0 if report.passed else 1

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0 if report.passed else 1

    _echo(
        f"Golden set: {report.total} questions | Retriever: {retriever_type} | top_k={report.top_k}"
    )
    _echo("")
    _echo(
        f"{'ID':<7} {'Status':<6} {'Rank':<8} {'P@3':<7} {'P@5':<7} {'Expected':<12} {'Question'}"
    )
    _echo("-" * 80)
    for outcome in report.outcomes:
        rank = f"rank {outcome.rank}" if outcome.rank else "--"
        p3 = f"{outcome.precision_at_3:.2f}"
        p5 = f"{outcome.precision_at_5:.2f}"
        exp = ",".join(outcome.question.expected_sections)
        _echo(
            f"{outcome.question.id:<7} {outcome.status:<6} {rank:<8} {p3:<7} {p5:<7} {exp:<12} {outcome.question.question[:40]}"
        )

    _echo("")
    _echo(
        f"Hit rate: {report.hits}/{report.total} ({report.hit_rate:.1%})   "
        f"target >= {TARGET_HIT_RATE:.0%}   "
        f"{'PASS' if report.passed else 'FAIL'}"
    )
    _echo(f"Mean Precision@3: {report.mean_precision_at_3:.2f}")
    _echo(f"Mean Precision@5: {report.mean_precision_at_5:.2f}")
    if report.hits:
        _echo(f"Mean rank of hits: {report.mean_hit_rank:.2f}")
    if report.misses:
        _echo("")
        _echo("Misses (retrieved sections shown for diagnosis):")
        for outcome in report.misses:
            _echo(
                f"  {outcome.question.id}  expected "
                f"{','.join(outcome.question.expected_sections)}  "
                f"got {','.join(outcome.retrieved_sections[:3])}"
            )

    return 0 if report.passed else 1


# ----------------------------------------------------------------------
# benchmark (Day 2 Comparative Matrix)
# ----------------------------------------------------------------------


def cmd_benchmark(args: argparse.Namespace) -> int:
    import json

    from backend.app.evaluation import evaluate, load_golden_questions
    from backend.app.retrieval.factory import get_retriever
    from backend.app.retrieval.store import VectorStore

    settings = get_settings()
    store = VectorStore(settings)
    if not store.is_ready():
        _echo("No index built. Run: python -m backend.app.cli ingest")
        return 1

    questions = load_golden_questions()
    _echo(f"Running Day 2 Benchmark across {len(questions)} queries...")

    configs = [
        ("dense", "Dense (Cosine)", "Section-Aware"),
        ("bm25", "BM25 (Lexical)", "Section-Aware"),
        ("hybrid", "Hybrid (Dense+BM25)", "Section-Aware"),
        ("hybrid_rerank", "Hybrid + Reranker", "Section-Aware"),
    ]
    depths = [3, 5, 10]

    comparison_results: list[dict] = []
    reports_map: dict[str, Any] = {}

    for rtype, rname, cconfig in configs:
        retriever = get_retriever(retriever_type=rtype, store=store, settings=settings)
        for depth in depths:
            rep = evaluate(
                retriever,
                questions=questions,
                top_k=depth,
                settings=settings,
                retriever_name=rname,
                chunking_config=cconfig,
            )
            key = f"{rtype}_k{depth}"
            reports_map[key] = rep
            comparison_results.append(
                {
                    "retriever": rname,
                    "type": rtype,
                    "depth": depth,
                    "hit_rate": rep.hit_rate,
                    "mean_hit_rank": rep.mean_hit_rank,
                    "mean_p3": rep.mean_precision_at_3,
                    "mean_p5": rep.mean_precision_at_5,
                    "passed": rep.passed,
                }
            )

    if args.json:
        payload = {
            "summary": comparison_results,
            "reports": {k: v.to_dict() for k, v in reports_map.items()},
        }
        output_str = json.dumps(payload, indent=2)
        if args.output:
            Path(args.output).write_text(output_str, encoding="utf-8")
            _echo(f"Benchmark written to {args.output}")
        else:
            print(output_str)
        return 0

    # Print summary table
    _echo("")
    _echo("=" * 80)
    _echo("DAY 2 RETRIEVAL BENCHMARK: COMPARATIVE SUMMARY")
    _echo("=" * 80)
    _echo(
        f"{'Retriever Strategy':<25} {'Top-k':<7} {'Hit Rate':<10} {'Mean Rank':<11} {'Mean P@3':<10} {'Mean P@5':<10} {'Status'}"
    )
    _echo("-" * 80)
    for res in comparison_results:
        status = "PASS" if res["passed"] else "FAIL"
        _echo(
            f"{res['retriever']:<25} {res['depth']:<7} {res['hit_rate']:<10.1%} {res['mean_hit_rank']:<11.2f} {res['mean_p3']:<10.2f} {res['mean_p5']:<10.2f} {status}"
        )

    # Detailed matrix for the primary hybrid_rerank configuration
    best_report = reports_map.get("hybrid_rerank_k5") or reports_map.get("hybrid_k5")
    if best_report:
        _echo("")
        _echo("=" * 80)
        _echo("EVALUATION TRACKING MATRIX (HYBRID + RERANK, TOP-5)")
        _echo("=" * 80)
        matrix_md = best_report.to_markdown_matrix()
        _echo(matrix_md)

        if args.output:
            full_md = (
                "# Retrieval Evaluation & Benchmark Report\n\n"
                "## Summary Comparison Table\n\n"
                "| Strategy | Top-$k$ | Hit Rate | Mean Hit Rank | Mean Precision@3 | Mean Precision@5 | Status |\n"
                "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |\n"
            )
            for res in comparison_results:
                full_md += (
                    f"| {res['retriever']} | {res['depth']} | {res['hit_rate']:.1%} | "
                    f"{res['mean_hit_rank']:.2f} | {res['mean_p3']:.2f} | {res['mean_p5']:.2f} | "
                    f"{'PASS' if res['passed'] else 'FAIL'} |\n"
                )
            full_md += f"\n\n## Primary Evaluation Tracking Matrix\n\n{matrix_md}\n"
            Path(args.output).write_text(full_md, encoding="utf-8")
            _echo(f"\nMarkdown benchmark report written to {args.output}")

    return 0


# ----------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m backend.app.cli",
        description="Clinical Decision Support Lite — ingestion, retrieval & evaluation.",
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
    query.add_argument(
        "--retriever-type",
        choices=["dense", "bm25", "hybrid", "hybrid_rerank"],
        default=None,
        help="Retrieval strategy (default: configured in settings).",
    )
    query.add_argument("--json", action="store_true", help="Emit SearchResponse JSON.")
    query.add_argument("--full-text", action="store_true", help="Print whole chunks, not excerpts.")
    query.set_defaults(func=cmd_query)

    evaluate_cmd = sub.add_parser(
        "eval", help="Run golden questions and report hit rate, Precision@3, and Precision@5."
    )
    evaluate_cmd.add_argument("--top-k", type=int, default=0, help="Retrieval depth.")
    evaluate_cmd.add_argument(
        "--retriever-type",
        choices=["dense", "bm25", "hybrid", "hybrid_rerank"],
        default=None,
        help="Retrieval strategy.",
    )
    evaluate_cmd.add_argument(
        "--matrix", action="store_true", help="Emit markdown evaluation matrix table."
    )
    evaluate_cmd.add_argument("--json", action="store_true", help="Emit JSON report.")
    evaluate_cmd.set_defaults(func=cmd_eval)

    benchmark_cmd = sub.add_parser(
        "benchmark", help="Run comprehensive multi-strategy, multi-depth evaluation benchmark."
    )
    benchmark_cmd.add_argument("--output", "-o", help="File path to save markdown or JSON report.")
    benchmark_cmd.add_argument("--json", action="store_true", help="Emit JSON instead of Markdown.")
    benchmark_cmd.set_defaults(func=cmd_benchmark)

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
