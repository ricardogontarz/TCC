# Normalização de OCR com RAG + LLM — Ferramenta do TCC

Pós-processador de OCR que usa **RAG (Retrieval-Augmented Generation) + LLM** para
converter o texto bruto de documentos escaneados (recibos) em **JSON estruturado**,
com baixa taxa de alucinação, validação humana e aprendizado contínuo.

Implementa a proposta de TCC *"Aplicação de Técnicas de RAG com LLMs para Normalização
e Otimização de OCRs"* (Ricardo Max Gontarz Junior — UTFPR Dois Vizinhos).

**Ground truth do projeto: SROIE (ICDAR 2019, Task 3)** — recibos reais escaneados,
anotados com 4 campos (`company`, `address`, `date`, `total`). Os campos padrão da
ferramenta são **os mesmos do gabarito** (derivados de `nucleo/schema.py`); o usuário
pode adicionar campos extras pela tela de Configurações.

## Mapeamento módulo → objetivo da proposta

| Objetivo específico | Onde está |
|---|---|
| **Obj 1** — pipeline Tesseract + embeddings + busca + LLM | `ocr.py` + `banco_vetorial.py` + `pipeline.py` (orquestração direta em Python — ver "Decisões de projeto") |
| **Obj 2** — banco vetorial indexando pares validados | `banco_vetorial.py` (ChromaDB) |
| **Obj 3** — validação humana com realimentação | `app.py` (frontend Streamlit) e `validacao.py` (terminal) — ambos gravam aprovados no banco |
| **Obj 4** — avaliação quantitativa COM vs SEM RAG | `avaliacao_sroie.py` (pareada, ground truth externo — SROIE/ICDAR 2019) |

## Persistência de dados (dois bancos, papéis distintos)

| Banco | Tecnologia | O que guarda |
|---|---|---|
| **Vetorial** | ChromaDB (`chroma_notas/`) | SÓ os pares (OCR → JSON) **já validados** — é a base de recuperação do RAG. Coleções separadas: `notas_v<versão>` (app, por versão de campos) e `sroie_trainval` (avaliação). |
| **Resultados** | SQLite (`resultados.db`, módulo `registro.py`) | **Toda extração executada** (app, CLI e harness): JSON gerado, documento de origem, timestamp, status da validação humana (`pendente`/`aprovado`/`rejeitado`), versão do pipeline (`config.PIPELINE_VERSAO`), provedor/modelo, RAG on/off, tempos, tokens e custo. |

Privacidade: `config.REGISTRAR_CONTEUDO = False` desliga a gravação de conteúdo
(OCR/JSON) no banco de resultados — para documentos reais com dados pessoais.

**Fluxo de inferência:** `imagem → OCR → busca de exemplos similares → prompt few-shot → LLM → JSON validado`
**Fluxo de aprendizado:** `JSON extraído → humano aprova/corrige → par (OCR, JSON) vetorizado e gravado`

## Estrutura

O código vive em `src/`, organizado em **três pacotes por responsabilidade**:
`nucleo/` (domínio: pipeline e persistência), `frontend/` (interface Streamlit) e
`experimentos/` (avaliação). Os pontos de entrada (`app.py`, `cli.py`) ficam na raiz
de `src/`. **Rode sempre a partir da raiz do projeto** — os caminhos relativos do
config (`./chroma_notas`, `dados/`) resolvem a partir dela.

```
src/
├── app.py                   # entrada do frontend Streamlit (roteador de páginas)
├── cli.py                   # entrada de linha de comando (mesma config de campos do app)
├── validacao.py             # M4 — validação humana via terminal (par da CLI)
├── nucleo/                  # DOMÍNIO: o pipeline e suas dependências centrais
│   ├── config.py            #   FONTE ÚNICA de config (embedding, paths, modelos, limiares)
│   ├── schema.py            #   ReciboSROIE (gabarito) + anotação tipo/rótulo (fonte única dos campos)
│   ├── ocr.py               #   M1 — Tesseract + pré-processamento OpenCV (idioma por chamada)
│   ├── banco_vetorial.py    #   M2 — ChromaDB (pares validados; metadados de rastreio)
│   ├── pipeline.py          #   M3 — extrair(): OCR → RAG → LLM → Pydantic + retry
│   ├── registro.py          #   banco de RESULTADOS (SQLite): toda extração + status + versão
│   ├── campos.py            #   campos configuráveis (padrão DERIVADO do gabarito) + versões
│   ├── schema_dinamico.py   #   monta schema Pydantic dos campos configurados
│   └── comum.py             #   utilitários do harness (slug, retry 429, pares img+json)
├── frontend/                # INTERFACE web (Streamlit)
│   ├── pagina_validacao.py  #   upload → extração → formulário → aprovar/corrigir/descartar
│   ├── pagina_dashboard.py  #   histórico de extrações (status/tempos) + resultados das avaliações
│   ├── pagina_configuracoes.py  # campos a extrair (versões v1, v2, …)
│   ├── servico_nota.py      #   regra de negócio do app (sem Streamlit; testável)
│   └── ui_estado/estilos/componentes.py  # session_state, CSS e widgets
└── experimentos/            # AVALIAÇÃO (reprodutível, fora do caminho de produção)
    ├── metricas.py          #   P/R/F1, alucinação, EM, limiares
    ├── sroie.py             #   dataset SROIE: preparo, indexação (só trainval), auditoria
    └── avaliacao_sroie.py   #   harness pareado: baseline (LLM puro) vs LLM + RAG
tests/               # pytest: métricas, registro e campos (python -m pytest tests/ -q)
campos.json          # campos configurados em runtime (gerado; defaults em campos.py)
dados/
├── sroie/           # SROIE: trainval/ (626, entram na base) + test/ (347, SÓ medem)
│                    #   + cache_ocr/ (OCR feito 1x por documento). Fora do git (540MB);
│                    #   monte com: python src/experimentos/sroie.py --preparar
└── aprovadas/       # documentos REAIS aprovados no app, por versão de campos (gerado)
docs/                # proposta do TCC (document_pdf.pdf) + esqueleto do relatório
resultados/          # artefatos das avaliações (CSV + MD + gráfico)
resultados.db        # banco de RESULTADOS (SQLite; gerado em runtime, fora do git)
chroma_notas/        # base vetorial persistida (gerada; fora do git)
```

## Instalação

**Dependências de sistema** (Tesseract — o inglês, idioma do SROIE, já vem no pacote base):
```bash
# macOS
brew install tesseract
# Debian/Ubuntu
sudo apt-get install tesseract-ocr
```
Confira: `tesseract --list-langs` deve listar `eng`. Para extrair documentos em outro
idioma, instale o pacote correspondente (ex.: `tesseract-lang` no macOS) e ajuste
`"idioma_ocr"` no `campos.json`.

**Dependências Python:**
```bash
pip install -r requirements.txt
```

**LLM — escolha o provedor em `config.py` (`PROVEDOR_LLM`):**

- **`ollama` (padrão, grátis e offline):** roda um modelo local, sem cota nem
  rate-limit. Instale e baixe o modelo uma vez:
  ```bash
  brew install --cask ollama-app   # NÃO use "brew install ollama" (fórmula
                                    # quebrada no macOS: falta o llama-server)
  ollama serve &                    # sobe o servidor local (porta 11434)
  ollama pull llama3.1:8b           # ~4.9GB (modelo de config.MODELO_OLLAMA)
  ```
- **`gemini` (online):** copie `.env.example` para `.env` e preencha `GOOGLE_API_KEY`.
  Atenção ao free tier (~10 req/min + cota diária).

## Como rodar

**1. Montar o dataset (1ª vez):**
```bash
python src/experimentos/sroie.py --preparar   # baixa 626 trainval + 347 teste (gabarito oficial)
```

**2. Extrair um documento (CLI):**
```bash
python src/cli.py --imagem dados/sroie/test/sroie_test_000.jpg            # COM RAG
python src/cli.py --imagem dados/sroie/test/sroie_test_000.jpg --sem-rag  # baseline (Obj 4)
# opcional: escolher LLM em tempo de execução (default vem do config)
python src/cli.py --imagem recibo.png --provedor ollama --modelo llama3.1:8b
```
✅ Resultado: texto OCR + JSON com os campos configurados (padrão: company/address/date/total).

**3. Validação humana (popula a base do app):**

Opção web (recomendada — ver seção "Frontend" abaixo):
```bash
python -m streamlit run src/app.py
```
Opção terminal:
```bash
python src/cli.py --imagem recibo.png --validar
```
Aprovar (`s`), corrigir (`c`) ou descartar (`n`). Só JSON válido entra na base.

**4. Avaliação pareada — baseline (LLM puro) vs LLM + RAG:**
```bash
# Experimento completo (indexa o trainval e avalia os 347 docs de teste
# nas DUAS condições — demora horas com LLM local):
python src/experimentos/avaliacao_sroie.py --recriar

# Smoke test rápido:
python src/experimentos/avaliacao_sroie.py --recriar --limite-indexacao 30 --limite 5
```
Regras do experimento (impostas no código, não por convenção):
- **Anti-leakage:** só o `trainval/` pode ser indexado (`experimentos/sroie.py`
  recusa caminhos de teste) e uma **auditoria** dos metadados da coleção roda
  antes de qualquer medição — se houver um doc de teste na base, a avaliação aborta.
- **Pareamento estrito:** o OCR de cada doc de teste é feito UMA vez (cache em
  `dados/sroie/cache_ocr/`) e baseline e RAG recebem o mesmo texto e o mesmo modelo.
- **Ground truth:** sempre o gabarito oficial do SROIE — o modelo nunca gera nem
  corrige a própria referência.
- **Métricas:** P/R/F1 por campo + micro; **taxa de alucinação** (campo errado vs
  gabarito E não derivável do OCR de entrada — limiar `config.LIMIAR_DERIVACAO`);
  taxa de erro "grounded"; exact match por documento; validade de JSON; tempo e
  custo por documento. Company/address casam por **similaridade de edição
  normalizada ≥ `config.LIMIAR_SIMILARIDADE` (0,80)**; datas como data
  normalizada; total como número (±0,01).

✅ Resultado: `resultados/sroie_<provedor-modelo>.csv` + `.md` (tabela pronta
para o relatório) + `.png` (F1 por campo, baseline vs RAG) — também visíveis na
página **Dashboard** do app.

⚠️ **Só se usar `--provedor gemini`:** o free tier limita ~10 req/min, então rode
com `--pausa 8` (o harness ainda re-tenta sozinho ao bater o limite). Com
**Ollama** (padrão) não há cota nem rate-limit.

## Frontend

```bash
python -m streamlit run src/app.py
# (se o console script estiver no PATH, `streamlit run src/app.py` também serve)
```

Tem **três páginas** (seletor na barra lateral):

**Página "Validação"** — cumpre o ciclo de validação humana da proposta (Objetivo 3),
com a comparação do Objetivo 4 **ao vivo**:

1. **Upload** da imagem do documento (PNG/JPG, **um por vez** — com um documento em
   revisão, o upload fica travado até aprovar/descartar); na **barra lateral**, escolha
   o **provedor** (Ollama/Gemini).
2. Clique **Extrair**: o sistema roda as **duas condições** — baseline (LLM puro) e
   LLM + RAG — sobre o **mesmo texto OCR** (pareamento estrito, igual ao harness) e
   mostra os dois resultados **lado a lado**, com nº de exemplos recuperados, tempo,
   tokens e os campos em que as condições **divergem destacados** (🟡).
3. A **revisão é sempre da versão COM RAG** (o baseline é só referência, somente
   leitura): o **formulário** vem pré-preenchido com os valores dela.
4. **Aprovar** / **Salvar correção** / **Descartar**. O formulário é validado pelo Pydantic
   antes de gravar. A versão COM RAG fica **aprovada** no banco de resultados e o baseline,
   **rejeitado** (descartar rejeita as duas). Cada aprovação vetoriza o par (OCR, JSON) e
   **faz a base crescer** (realimentação — o contador na barra lateral sobe). Na próxima
   extração, a condição COM RAG já recupera esses exemplos.
5. No rodapé, um expander mostra as **médias históricas por condição** (tempo do LLM e
   tokens, COM vs SEM RAG) — a mesma tabela da página Dashboard, como contexto.

> A base do app (`notas_v<versão>`) começa **vazia** — nas primeiras extrações a condição
> "COM RAG" opera como LLM puro (cold start, indicado no cartão). Para já partir com
> exemplos, **semeie a base do app com o trainval do SROIE** (idempotente; só trainval —
> teste continua proibido em qualquer base):
> ```bash
> python src/experimentos/sroie.py --semear-app
> ```
> As coleções continuam separadas: a do experimento (`sroie_trainval`) fica intocada e
> auditável; as aprovações do app entram só na coleção do app.

**Página "Dashboard"** — visão consolidada (somente leitura), em duas abas:
**Extrações** (status da validação humana; **custo em US$ e R$** — câmbio em
`config.CAMBIO_USD_BRL`, preços por modelo em `registro.PRECO_POR_MILHAO`;
tempos/tokens/custo médios por condição RAG; volume por experimento e por dia;
tabela das recentes) e **Avaliações** (tabelas, gráficos e CSVs baseline vs RAG
de `resultados/`). O filtro de experimento traz App e SROIE (o `cli` fica fora
das opções; "Todos" conta tudo).

**Página "Configurações"** — define **quais campos** o sistema espera extrair:

- **Os campos PADRÃO são os do ground truth** (SROIE: `company`, `address`, `date`,
  `total`), **derivados do schema anotado** em `nucleo/schema.py` — fonte única: os
  campos usados para validar são, por construção, os mesmos do formulário e do prompt.
- **Campos extras**: adicionar (rótulo + tipo: texto/número/data) ou remover — a única
  diferença em relação ao gabarito é poder acrescentar valores a mais.
- **Lista de itens** (opcional, desligada por padrão — o SROIE não anota itens): liga uma
  tabela de itens com colunas configuráveis (descrição/qtd/valor unitário e extras).
- Esses campos montam **o prompt de extração, o formulário de revisão e a validação** —
  adicionar "VAT", por exemplo, passa a pedir e a mostrar esse campo. Tudo salvo em `campos.json`.
- **Versão dos campos (v1, v2, …)**: a configuração de campos é versionada. Mudar QUALQUER campo
  gera uma **versão nova**; voltar a uma configuração anterior **reusa** a versão dela.
  A versão atual aparece na barra lateral (Validação) e no topo de Configurações.
- **Uma base por versão**: cada versão usa sua própria coleção Chroma (`notas_v<versão>`) e sua
  própria pasta de aprovados (`dados/aprovadas/v<versão>/`). Assim, **mudar campos não afeta os
  resultados de versões anteriores** — e a base do app fica isolada da coleção da avaliação
  (`sroie_trainval`).
- ⚠️ Isso afeta o **app/CLI (produção)**. A avaliação baseline vs RAG segue no
  **schema fixo** (`schema.ReciboSROIE`) de propósito — o experimento controlado, com gabarito fixo.

> ⚠️ Rode a partir da **raiz** do projeto (`python -m streamlit run src/app.py`), nunca de dentro de `src/`,
> senão `./chroma_notas` e `dados/` apontariam para o lugar errado.
>
> Hoje a UI aceita **imagens** (PNG/JPG). Suporte a **PDF** é uma extensão futura (exigiria
> `poppler`/`pdf2image` para rasterizar antes do OCR).

## Decisões de projeto (para a defesa)

- **Orquestração direta em Python (em vez de Langflow):** a proposta previa orquestrar o
  pipeline no **Langflow** (prototipação visual). Durante o desenvolvimento, optou-se por uma
  implementação **direta em Python**, por três motivos defensáveis: **(1) controle e
  testabilidade** — o pipeline em código permite tratamento de erro explícito (retry +
  validação Pydantic como freio anti-alucinação), versionamento por git e execução
  reprodutível, o que um fluxo visual dificulta; **(2) menos dependências e reprodutibilidade**
  — não acopla o experimento a uma plataforma e a uma versão específica do Langflow;
  **(3) o objetivo científico** (medir RAG vs não-RAG, Obj 4) exige um harness de avaliação
  determinístico, naturalmente expresso em código (`avaliacao_sroie.py`). O frontend Streamlit
  (`app.py`) entrega a interface de upload + seleção de modelo + validação humana que a
  proposta pede.
- **Ground truth externo (SROIE):** o gabarito vem de um dataset público e revisado
  (ICDAR 2019), nunca do próprio modelo — elimina o viés de o sistema "corrigir a própria
  prova". O split treino/teste oficial é a fonte única de verdade no código (diretórios
  `trainval/` e `test/`), com salvaguardas estruturais contra vazamento.
- **Provedor de LLM configurável:** `config.PROVEDOR_LLM` alterna entre `ollama`
  (modelo local, grátis, offline, sem cota — **padrão**) e `gemini` (API do Google).
  A proposta citava `gemini-2.0-flash`, mas ele não está no free tier desta conta
  (cota = 0); por isso o padrão passou a ser um LLM local via Ollama (`llama3.1:8b`),
  com o Gemini gratuito como alternativa online. Isso permite defender o experimento
  RAG vs não-RAG sem depender de cota de API, e até comparar provedores.
- **Anti-alucinação (dois freios + métrica honesta):** o prompt instrui "campo ausente =
  null, nunca invente"; o schema Pydantic é opcional + validado, com **1 retry** anexando o
  erro. Na avaliação, **alucinação** = campo errado vs gabarito **E** não derivável do OCR de
  entrada (correções legítimas de ruído de OCR não contam); erro presente no OCR é medido à
  parte ("erro grounded").
- **Cold start:** com a base vazia, o pipeline opera como LLM puro — não é erro.

## Limitação registrada

O domínio avaliado é o do SROIE: recibos de varejo em inglês, escaneados. A
generalização para outros tipos de documento (ex.: notas fiscais brasileiras) é
suportada pela ferramenta (campos e idioma de OCR configuráveis), mas não foi
medida com ground truth próprio.

Fonte do dataset SROIE: espelho HuggingFace `rth/sroie-2019-v2` do dataset
oficial (https://rrc.cvc.uab.es/?ch=13), splits originais preservados
(626 trainval / 347 teste), licença CC-BY-2.0.

## Pendências

- (Opcional futuro) Suporte a upload de **PDF** no frontend (rasterizar com `poppler`/`pdf2image`
  antes do OCR; hoje só imagem).
- (Opcional) Análise de sensibilidade do limiar de similaridade (0,75/0,80/0,85/0,90)
  e ablação do k de exemplos recuperados.
