### SROIE (ICDAR 2019) — baseline vs RAG — ollama / llama3.1:8b

- Documentos de teste: **347** (base RAG: trainval, auditada contra leakage)
- Limiar de similaridade (company/address): **0.8** | limiar de derivação (alucinação): **0.7** | pipeline v2.0.0

| Campo | P (base) | R (base) | F1 (base) | P (RAG) | R (RAG) | F1 (RAG) |
|---|---|---|---|---|---|---|
| company | 0.718 | 0.602 | 0.655 | 0.872 | 0.824 | 0.847 |
| address | 0.732 | 0.331 | 0.456 | 0.877 | 0.801 | 0.837 |
| date | 0.688 | 0.548 | 0.610 | 0.770 | 0.628 | 0.692 |
| total | 0.584 | 0.461 | 0.515 | 0.684 | 0.481 | 0.565 |
| **micro** | 0.675 | 0.486 | 0.565 | 0.810 | 0.684 | 0.741 |

| Métrica | Baseline (LLM puro) | LLM + RAG |
|---|---|---|
| Taxa de alucinação (principal) | 0.098 | 0.087 |
| Taxa de erro grounded | 0.226 | 0.103 |
| Exact match (documento) | 0.127 | 0.323 |
| JSON válido (1ª tentativa) | 1.000 | 0.919 |
| JSON válido (final) | 1.000 | 0.977 |
| Tempo LLM médio/doc (s) | 4.7 | 8.5 |
| Tokens médios (entrada) | 714 | 1997 |
| Custo médio/doc (US$) | 0.0000 | 0.0000 |
