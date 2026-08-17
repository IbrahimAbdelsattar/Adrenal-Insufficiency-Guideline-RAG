# Hands-on Lab: Retrieval Evaluation & Optimization
**Event:** AI Clinical Decision Support Lite Hackathon  
**Focus:** Retrieval & Evaluation Before Prompt Finalization

---

> [!CAUTION]
> **Stop Point:** Do not finalize generation prompts until retrieval can surface the correct evidence consistently.

---

## 🎯 Lab Objectives & Overview

The goal of this hands-on lab is to systematically evaluate, benchmark, and optimize the retrieval layer of your RAG / Clinical Decision Support pipeline before moving forward to prompt engineering and LLM response generation.

---

## 📋 Requirements & Checklist

### 1. 🔍 Query Benchmark Setup
- [ ] Curate a test dataset of **15–20 representative questions / clinical queries**.
- [ ] Run **Top-5 search** across all 15–20 benchmark queries.

### 2. 📊 Retrieval & Inspection
- [ ] Display all retrieved chunks alongside their:
  - Text content
  - Metadata (source document, section, chunk ID, page number)
  - Similarity / relevance scores

### 3. 🏷️ Relevance Labeling (Ground Truth)
- [ ] For each retrieved chunk across every query, annotate/label whether it is:
  - `Relevant (1)`: Contains ground-truth clinical evidence addressing the question.
  - `Not Relevant (0)`: Distracting, off-topic, or missing critical context.

### 4. 📈 Metrics Calculation
- [ ] Calculate **Precision@3** for each query and across the dataset.
- [ ] Calculate **Precision@5** for each query and across the dataset.

$$\text{Precision@}k = \frac{\text{Number of Relevant Chunks in Top-}k}{k}$$

### 5. ⚙️ Chunking Strategy Comparison
- [ ] Compare at least **two different chunking configurations** (e.g.):
  - **Configuration A:** Fixed-size small chunks (e.g., 256 tokens, 10% overlap)
  - **Configuration B:** Semantic / larger chunks (e.g., 512–1024 tokens, markdown/header splitting)

### 6. 🎛️ Top-k Retrieval Depth Analysis
- [ ] Test and compare performance across:
  - **Top-3**
  - **Top-5**
  - **Top-10**

### 7. 🚀 Advanced Retrieval (Optional / Bonus)
- [ ] Implement & evaluate **Hybrid Search** (Dense Vector Embeddings + Sparse BM25 / Keyword search).
- [ ] Test a **Reranking Step** (e.g., Cross-Encoder / Cohere Rerank) on candidate chunks.

### 8. 📝 Findings & Documentation
- [ ] Document which configuration yielded the highest retrieval accuracy and precision.
- [ ] Detail *why* specific setups succeeded or failed (e.g., chunk boundary issues, terminology mismatch, semantic drift).

---

## 📐 Evaluation Tracking Matrix Template

| Query # | Query Description | Chunking Config | Top-$k$ | Precision@3 | Precision@5 | Notes / Failure Modes |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Q01** | *[Clinical Query 1]* | Config A | 5 | $0.67$ | $0.60$ | Missed dosage footnote |
| **Q01** | *[Clinical Query 1]* | Config B (Hybrid) | 5 | $1.00$ | $0.80$ | Complete guideline context captured |
| ... | ... | ... | ... | ... | ... | ... |

---

## 🏁 Deliverables & Completion Criteria

1. **Benchmark Results:** Tabulated evaluation dataset with 15–20 queries, labeled chunks, and computed Precision@3 and Precision@5.
2. **Comparison Summary:** Side-by-side analysis comparing chunking strategies, retrieval depths (Top-3 vs Top-5 vs Top-10), and optional hybrid/reranking results.
3. **Go/No-Go Decision:** Verified that retrieval consistency satisfies downstream generation requirements before building clinical prompts.
