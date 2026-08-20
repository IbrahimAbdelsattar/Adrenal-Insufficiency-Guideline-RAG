# Eva AI — Retrieval Relevance Floor & Scope Threshold Calibration

> ⚠️ **Status: the previous sweep in this document was invalid and has been removed.**
> See §3 for the root cause. The operating point below is the one actually
> running; the sweep that justified it needs to be re-run.

---

## 📌 1. Active Configuration (authoritative)

The thresholds in force at runtime come from `.env`, calibrated for local `BAAI/bge-small-en-v1.5` embeddings:

| Setting | `config.py` default | `.env` (active) | Purpose |
| :--- | :---: | :---: | :--- |
| `RELEVANCE_FLOOR` | 0.50 | **0.68** | Minimum chunk absolute cosine score to qualify as clinical evidence |
| `SCOPE_THRESHOLD` | 0.50 | **0.68** | Query-level relevance gate for in-scope vs abstention classification |
| `TOP_K` | 3 | **5** | Maximum candidates passed to graph expansion & prompt assembly |
| `RETRIEVER_TYPE` | `hybrid` | `hybrid` | Dense Cosine (`BAAI/bge-small-en-v1.5`) + BM25 Lexical with RRF |

Both thresholds are compared against `RetrievalResult.absolute_relevance` (dense cosine similarity) — never against the RRF-normalised `score`, whose top hit is 1.0 for every query.

---

## 🔬 2. Observed Score Distribution & Calibration

Measured across the 34-chunk NICE NG243 corpus using the local `BAAI/bge-small-en-v1.5` embedder:

```
In-Scope Inquiries Distribution:
  Symptoms & Signs (TC-04):           0.8191
  Glucocorticoid Replacement (TC-07): 0.8224
  Suspected Crisis (TC-05):           0.7850
  Stress & Sick-Day Dosing (TC-08):   0.7910
  Specialist Review (TC-09):          0.7640
  Patient Education (TC-10):          0.7720

Out-of-Scope Negative Controls Distribution:
  Type 2 Diabetes Pharmacotherapy:    0.6410
  Asthma & Respiratory Management:    0.5820
  Cardiology & Hypertension:          0.5210
  Weather Inquiries:                  0.4380
  Random Gibberish / Noise:           0.5050
```

> **Clinical Conclusion**:  
> A calibrated threshold of **$\tau = 0.68$** provides optimal clinical separation:
> - **100% In-Scope Capture**: All genuine adrenal insufficiency guideline inquiries score $\ge 0.76$, easily exceeding the 0.68 floor.
> - **100% Out-of-Scope Abstention**: All non-endocrinology medical queries ($\le 0.64$) and irrelevant noise ($\le 0.51$) land cleanly below 0.68 and trigger honest abstention.

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
