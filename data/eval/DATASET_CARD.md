# Eva AI — Clinical Decision Support Evaluation Dataset Card

## 1. Dataset Overview

The **Eva AI Clinical Evaluation Dataset** is a clinician-curated benchmark designed to rigorously assess the retrieval precision, citation faithfulness, clinical safety, dosage accuracy, and hallucination resistance of Retrieval-Augmented Generation (RAG) systems targeting **NICE guideline NG243 (Adrenal Insufficiency: Identification and Management)**.

- **Total Test Cases**: 45
- **Retrieval Goldens**: 20
- **Generation & Safety Scenarios**: 25
- **Emergency Zero-Tolerance Cases**: 15
- **Abstention & Refusal Scenarios**: 4
- **Target Guideline**: NICE NG243 (Published August 2024)

---

## 2. Category Distribution

| Category | Cases Count | Primary Evaluation Focus |
| :--- | :---: | :--- |
| `adversarial_security` | 2 | Evaluates adversarial security compliance |
| `ambiguous_inquiry` | 1 | Evaluates ambiguous inquiry compliance |
| `bilingual_arabic` | 2 | Evaluates bilingual arabic compliance |
| `emergency_treatment` | 3 | Evaluates emergency treatment compliance |
| `out_of_scope` | 3 | Evaluates out of scope compliance |
| `patient_education` | 1 | Evaluates patient education compliance |
| `pediatric_dosing` | 2 | Evaluates pediatric dosing compliance |
| `pregnancy_perioperative` | 3 | Evaluates pregnancy perioperative compliance |
| `primary_vs_secondary` | 2 | Evaluates primary vs secondary compliance |
| `retrieval_ground_truth` | 20 | Evaluates retrieval ground truth compliance |
| `safety_guardrail` | 3 | Evaluates safety guardrail compliance |
| `sick_day_rules` | 2 | Evaluates sick day rules compliance |
| `steroid_withdrawal` | 1 | Evaluates steroid withdrawal compliance |

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
