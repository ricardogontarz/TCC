### SROIE (ICDAR 2019) — baseline vs RAG — ollama / qwen3:8b

- Documentos de teste: **347** (base RAG: trainval, auditada contra leakage)
- Limiar de similaridade (company/address): **0.8** | limiar de derivação (alucinação): **0.7** | pipeline v2.1.0

| Campo | P (base) | R (base) | F1 (base) | P (RAG) | R (RAG) | F1 (RAG) |
|---|---|---|---|---|---|---|
| company | 0.643 | 0.608 | 0.625 | 0.859 | 0.827 | 0.843 |
| address | 0.789 | 0.744 | 0.766 | 0.919 | 0.885 | 0.902 |
| date | 0.648 | 0.594 | 0.620 | 0.680 | 0.669 | 0.674 |
| total | 0.691 | 0.651 | 0.671 | 0.705 | 0.683 | 0.694 |
| **micro** | 0.693 | 0.649 | 0.670 | 0.790 | 0.766 | 0.778 |

| Métrica | Baseline (LLM puro) | LLM + RAG |
|---|---|---|
| Taxa de alucinação (principal) | 0.077 | 0.098 |
| Taxa de erro grounded | 0.230 | 0.112 |
| Exact match (documento) | 0.288 | 0.487 |
| JSON válido (1ª tentativa) | 0.997 | 0.867 |
| JSON válido (final) | 1.000 | 1.000 |
| Tempo LLM médio/doc (s) | 6.3 | 11.0 |
| Tokens médios (entrada) | 840 | 2489 |
| Custo médio/doc (US$) | 0.0000 | 0.0000 |
