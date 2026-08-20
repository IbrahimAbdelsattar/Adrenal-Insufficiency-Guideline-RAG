# Eva AI — Retrieval Relevance Floor & Scope Threshold Calibration

> ⚠️ **Status: the previous sweep in this document was invalid and has been removed.**
> See §3 for the root cause. The operating point below is the one actually
> running; the sweep that justified it needs to be re-run.

---

## 📌 1. Active Configuration (authoritative)

The thresholds in force at runtime come from `.env`, which **overrides** the
defaults in `backend/app/config.py`:

| Setting | `config.py` default | `.env` (active) |
| :--- | :---: | :---: |
| `RELEVANCE_FLOOR` | 0.50 | **0.70** |
| `SCOPE_THRESHOLD` | 0.50 | **0.68** |
| `TOP_K` | 3 | **5** |
| `RETRIEVER_TYPE` | `hybrid` | `hybrid` (reranker off) |

Both thresholds are compared against `RetrievalResult.absolute_relevance`
(dense cosine, or the cross-encoder score when reranking is enabled) — never
against the RRF-normalised `score`, whose top hit is 1.0 for every query.

---

## 🔬 2. Observed Score Behaviour

On the current 34-chunk NG243 index, in-scope queries land at roughly
0.667–0.810 absolute relevance and unrelated queries at 0.000–0.526, which is
the separation the 0.70 floor is placed inside.

Measured effect of the guardrail stack at this operating point, from the
25-case clinical evaluation:

- Out-of-scope refusals: **3/3 correct** (cardiology, asthma, diabetes)
- Adversarial prompt injection: **2/2 blocked**
- Correct abstention rate: **88.0%** against a ≥95% gate — the misses are
  **over**-refusals of valid in-scope questions, not leaked out-of-scope answers

Two Arabic clinical queries and one negation-correction query were refused in
under 90 ms, before retrieval ran. That is the current cost of this operating
point and the reason the gate fails.

---

## 🐞 3. Why the Previous Sweep Was Invalid

The earlier version of this document reported a threshold sweep in which every
candidate τ produced **Sensitivity 100.0% / Specificity 0.0%** and an in-scope
score distribution with `Min = Max = 0.5500` but `Median = 0.7180` — values that
cannot describe a real distribution.

Root cause: the Chroma index contained a leftover CI stub collection
`guidelines_local` with **2 records at dimension 4**, created by
`scripts/build_stub_index.py`. Because the local 384-dim BGE embedder routes to
that fallback collection, every dense query raised
`Collection expecting embedding with dimension of 4, got 384` and the hybrid
retriever silently degraded to **BM25-only**. BM25-only scoring collapsed the
relevance signal to a constant 0.5500 for every query — which is exactly the
"impossible" distribution above.

Dropping the stub collection restored dense retrieval (`guidelines_local` is now
auto-repopulated with all 34 chunks at 384 dims) and moved the clinical
evaluation from 64.0% to 80.0% overall pass rate, with out-of-scope refusal
going from 0% to 100%.

---

## ⚙️ 4. To Re-Run the Calibration

```bash
python scripts/calibrate_retrieval_threshold.py
```

Before trusting the output, confirm the index has no stub collections:

```bash
python -c "import chromadb; c=chromadb.PersistentClient(path='data/index'); print([(x.name, c.get_collection(x.name).count()) for x in c.list_collections()])"
```

Every collection should report **34** records. Any collection with 2 records at
dimension 4 is a CI stub and must be deleted before calibrating.
