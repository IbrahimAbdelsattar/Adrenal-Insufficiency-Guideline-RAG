"""Eva AI — Clinical Evaluation Dataset Builder & Exporter.

Compiles, validates, and exports the unified clinical evaluation dataset for
Eva AI (NICE NG243: Adrenal Insufficiency).

Outputs:
1. data/eval/evaluation_dataset.json (Full structured dataset)
2. data/eval/evaluation_dataset.jsonl (Standard RAG benchmarking format)
3. data/eval/evaluation_dataset.csv (Clinician review spreadsheet)
4. data/eval/DATASET_CARD.md (Dataset card & documentation)
"""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

import yaml

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

# Ensure repository root is in python path
ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

RETRIEVAL_DATASET_PATH = ROOT_DIR / "backend/tests/eval/golden_questions.yaml"
GENERATION_DATASET_PATH = ROOT_DIR / "backend/tests/eval/golden_generation.yaml"
OUTPUT_DIR = ROOT_DIR / "data/eval"


def load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Missing evaluation file: {path}")
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def build_unified_dataset() -> list[dict[str, Any]]:
    unified: list[dict[str, Any]] = []

    # 1. Ingest Retrieval Golden Questions
    retrieval_data = load_yaml(RETRIEVAL_DATASET_PATH)
    questions = retrieval_data.get("questions", [])

    for q in questions:
        item = {
            "eval_id": f"RET_{q['id']}",
            "eval_type": "retrieval_benchmark",
            "category": "retrieval_ground_truth",
            "is_emergency": any(sec in q.get("expected_sections", []) for sec in ["1.6", "1.7"]),
            "query": q["question"],
            "should_abstain": False,
            "expected_doc_id": q.get("expected_doc_id", "nice_ng243"),
            "expected_sections": q.get("expected_sections", []),
            "expected_recommendation_ids": q.get("expected_recommendation_ids", []),
            "must_include": [],
            "must_include_any": [],
            "must_not_include": [],
            "critical_medication_check": None,
            "clinical_notes": q.get("notes", ""),
        }
        unified.append(item)

    # 2. Ingest Generation Clinical Scenarios
    generation_data = load_yaml(GENERATION_DATASET_PATH)
    cases = generation_data.get("cases", [])

    for c in cases:
        item = {
            "eval_id": f"GEN_{c['id']}",
            "eval_type": "generation_safety_benchmark",
            "category": c.get("category", "general"),
            "is_emergency": c.get("is_emergency", False),
            "query": c["query"],
            "should_abstain": c.get("should_abstain", False),
            "expected_doc_id": "nice_ng243" if not c.get("should_abstain", False) else None,
            "expected_sections": c.get("expected_sections", []),
            "expected_recommendation_ids": c.get("expected_recommendations", []),
            "must_include": c.get("must_include", []),
            "must_include_any": c.get("must_include_any", []),
            "must_not_include": c.get("must_not_include", []),
            "critical_medication_check": c.get("critical_medication_check"),
            "clinical_notes": c.get("notes", ""),
        }
        unified.append(item)

    return unified


def export_json(dataset: list[dict[str, Any]], path: Path) -> None:
    path.write_text(json.dumps({"dataset_version": "1.0.0", "total_cases": len(dataset), "cases": dataset}, indent=2, ensure_ascii=False), encoding="utf-8")


def export_jsonl(dataset: list[dict[str, Any]], path: Path) -> None:
    lines = [json.dumps(item, ensure_ascii=False) for item in dataset]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_csv(dataset: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "eval_id",
        "eval_type",
        "category",
        "is_emergency",
        "should_abstain",
        "query",
        "expected_sections",
        "expected_recommendation_ids",
        "must_include",
        "must_not_include",
        "clinical_notes",
    ]
    with open(path, mode="w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for item in dataset:
            row = dict(item)
            row["expected_sections"] = ", ".join(item.get("expected_sections") or [])
            row["expected_recommendation_ids"] = ", ".join(item.get("expected_recommendation_ids") or [])
            row["must_include"] = "; ".join(item.get("must_include") or [])
            row["must_not_include"] = "; ".join(item.get("must_not_include") or [])
            writer.writerow(row)


def export_dataset_card(dataset: list[dict[str, Any]], path: Path) -> None:
    total = len(dataset)
    retrieval_count = sum(1 for d in dataset if d["eval_type"] == "retrieval_benchmark")
    gen_count = sum(1 for d in dataset if d["eval_type"] == "generation_safety_benchmark")
    emergency_count = sum(1 for d in dataset if d["is_emergency"])
    abstain_count = sum(1 for d in dataset if d["should_abstain"])

    categories: dict[str, int] = {}
    for d in dataset:
        cat = d["category"]
        categories[cat] = categories.get(cat, 0) + 1

    content = f"""# Eva AI — Clinical Decision Support Evaluation Dataset Card

## 1. Dataset Overview

The **Eva AI Clinical Evaluation Dataset** is a clinician-curated benchmark designed to rigorously assess the retrieval precision, citation faithfulness, clinical safety, dosage accuracy, and hallucination resistance of Retrieval-Augmented Generation (RAG) systems targeting **NICE guideline NG243 (Adrenal Insufficiency: Identification and Management)**.

- **Total Test Cases**: {total}
- **Retrieval Goldens**: {retrieval_count}
- **Generation & Safety Scenarios**: {gen_count}
- **Emergency Zero-Tolerance Cases**: {emergency_count}
- **Abstention & Refusal Scenarios**: {abstain_count}
- **Target Guideline**: NICE NG243 (Published August 2024)

---

## 2. Category Distribution

| Category | Cases Count | Primary Evaluation Focus |
| :--- | :---: | :--- |
"""
    for cat, count in sorted(categories.items()):
        content += f"| `{cat}` | {count} | Evaluates {cat.replace('_', ' ')} compliance |\n"

    content += """
---

## 3. Dataset Files

- `evaluation_dataset.json`: Full hierarchical structured schema with critical medication objects and negative constraints.
- `evaluation_dataset.jsonl`: Line-delimited JSON for direct ingestion into RAG benchmarking pipelines (e.g. Ragas, DeepEval).
- `evaluation_dataset.csv`: Flat tabular export for clinician review and manual audit.

---

## 4. Evaluation Dimensions & Release Gates

1. **Retrieval Recall@K**: Verifies that ground-truth guideline sections (1.1 to 1.9) appear in the top-K chunks.
2. **Citation Precision & Completeness**: Verifies structural citation tags (`[nice_ng243, Section X.Y, p. Z]`).
3. **Critical Medication Verification**: Exact drug (`hydrocortisone`), exact dose (`100 mg`), and valid parenteral route (`IM/IV`).
4. **Negative Constraints & Safety Guardrails**: Prevents dangerous advice (e.g., stopping steroids during sepsis, crushing oral tablets for IV).
5. **Fail-Closed Abstention**: Refuses out-of-scope queries (Cardiology, Asthma, Diabetes) and adversarial prompt injection attempts.
"""
    path.write_text(content, encoding="utf-8")


def main() -> None:
    print("=" * 70)
    print("Building Eva AI Clinical Evaluation Dataset...")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dataset = build_unified_dataset()

    json_path = OUTPUT_DIR / "evaluation_dataset.json"
    jsonl_path = OUTPUT_DIR / "evaluation_dataset.jsonl"
    csv_path = OUTPUT_DIR / "evaluation_dataset.csv"
    card_path = OUTPUT_DIR / "DATASET_CARD.md"

    export_json(dataset, json_path)
    export_jsonl(dataset, jsonl_path)
    export_csv(dataset, csv_path)
    export_dataset_card(dataset, card_path)

    print(f"✓ Unified dataset compiled successfully with {len(dataset)} cases:")
    print(f"  - JSON  : {json_path}")
    print(f"  - JSONL : {jsonl_path}")
    print(f"  - CSV   : {csv_path}")
    print(f"  - Card  : {card_path}")
    print("=" * 70)


if __name__ == "__main__":
    main()
