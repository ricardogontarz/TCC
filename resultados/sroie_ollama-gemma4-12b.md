### SROIE (ICDAR 2019) — baseline vs RAG — ollama / gemma4:12b

- Documentos de teste: **347** (base RAG: trainval, auditada contra leakage)
- Limiar de similaridade (company/address): **0.8** | limiar de derivação (alucinação): **0.7** | pipeline v2.1.0

| Campo | P (base) | R (base) | F1 (base) | P (RAG) | R (RAG) | F1 (RAG) |
|---|---|---|---|---|---|---|
| company | 0.760 | 0.720 | 0.740 | 0.904 | 0.870 | 0.887 |
| address | 0.859 | 0.810 | 0.834 | 0.910 | 0.873 | 0.891 |
| date | 0.711 | 0.646 | 0.677 | 0.756 | 0.697 | 0.726 |
| total | 0.723 | 0.663 | 0.692 | 0.800 | 0.738 | 0.768 |
| **micro** | 0.764 | 0.710 | 0.736 | 0.844 | 0.795 | 0.819 |

| Métrica | Baseline (LLM puro) | LLM + RAG |
|---|---|---|
| Taxa de alucinação (principal) | 0.062 | 0.074 |
| Taxa de erro grounded | 0.174 | 0.082 |
| Exact match (documento) | 0.380 | 0.530 |
| JSON válido (1ª tentativa) | 1.000 | 0.925 |
| JSON válido (final) | 1.000 | 1.000 |
| Tempo LLM médio/doc (s) | 15.8 | 18.7 |
| Tokens médios (entrada) | 896 | 2410 |
| Custo médio/doc (US$) | 0.0000 | 0.0000 |
