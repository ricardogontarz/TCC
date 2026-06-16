"""
Configuração central — FONTE ÚNICA de verdade do projeto.
=========================================================
Restrição crítica nº 1 do TCC: o modelo de embedding, o caminho de persistência
e o nome da collection PRECISAM ser idênticos em todo lugar que toca o banco
vetorial (gravação no pipeline, leitura na avaliação e na validação humana).
Se algum desses valores divergir, a busca semântica passa a devolver lixo
silenciosamente. Por isso eles moram aqui e são importados por todos os módulos.
"""

from pathlib import Path

# --- Banco vetorial (ChromaDB) ---------------------------------------------
# Caminho de persistência local do Chroma, compartilhado por todos os módulos
# que tocam a base (pipeline, avaliação e frontend). Cada consumidor passa o
# nome da SUA coleção (app: notas_v<versão>; avaliação: NOME_COLECAO_SROIE).
CAMINHO_CHROMA: str = "./chroma_notas"

# Modelo de embedding multilíngue. Tem que ser idêntico
# entre gravação e leitura, senão os vetores ficam em espaços diferentes.
MODELO_EMBEDDING: str = "paraphrase-multilingual-MiniLM-L12-v2"

# --- LLM (provedor configurável) --------------------------------------------
# Escolhe qual backend de LLM o pipeline usa. Trocar aqui afeta TODO o sistema
# (CLI, avaliação M5 e qualquer outro consumidor) — é o único ponto de mudança.
#   "ollama" -> modelo LOCAL, 100% grátis, sem cota nem rate-limit, offline.
#   "gemini" -> API do Google (free tier limitado: ~10 req/min e cota diária).
PROVEDOR_LLM: str = "ollama"

# Modelo usado quando PROVEDOR_LLM == "ollama" (roda na máquina via Ollama).
# llama3.1:8b é um bom equilíbrio para um Apple M3 Pro 18GB; alternativas:
# "qwen2.5:7b" (forte em JSON/multilíngue) ou "gemma2:9b".
MODELO_OLLAMA: str = "llama3.1:8b"
OLLAMA_HOST: str = "http://localhost:11434"

# Modelos Ollama OFERECIDOS no seletor do app (lista curada de propósito): são
# exatamente os avaliados no experimento SROIE, todos ~8-12B e capazes de gerar
# JSON estruturado limpo. NÃO incluir modelos de raciocínio puro (ex.:
# deepseek-r1): com o raciocínio ligado o traço <think> vaza e quebra o JSON, e
# desligado a saída degrada — não servem para extração estruturada constrita.
# O primeiro da lista é o padrão (MODELO_OLLAMA).
MODELOS_OLLAMA: tuple = ("llama3.1:8b", "qwen3:8b", "gemma4:12b")

# Modelo usado quando PROVEDOR_LLM == "gemini". A chave (GOOGLE_API_KEY) vem do
# .env, nunca hardcoded. Obs.: a proposta citava "gemini-2.0-flash", mas esse
# modelo não está no free tier desta conta (cota diária = 0); usamos o sucessor
# gratuito.
MODELO_LLM: str = "gemini-3.1-flash-lite"

# --- Versão do pipeline -------------------------------------------------------
# Carimbada em CADA extração registrada no banco de resultados (registro.py).
# Aumente sempre que mudar prompt, lógica de retry, OCR ou recuperação — é o que
# permite saber qual versão da ferramenta produziu cada resultado.
PIPELINE_VERSAO: str = "2.1.0"

# --- Custo ---------------------------------------------------------------------
# Câmbio usado SÓ para EXIBIR o custo também em reais (a contabilidade interna é
# em US$, moeda dos preços de API). Atualize antes de reportar R$ no relatório.
CAMBIO_USD_BRL: float = 5.40

# --- Banco de RESULTADOS (SQLite) --------------------------------------------
# Histórico de TODAS as extrações (aprovadas ou não), com status de validação
# humana e a versão do pipeline. Diferente do banco vetorial: o Chroma guarda só
# os pares VALIDADOS (recuperação do RAG); o SQLite guarda o histórico completo.
CAMINHO_REGISTRO: str = "resultados.db"

# Privacidade: com False, o texto OCR e o JSON extraído NÃO são gravados no
# banco de resultados (só metadados). Use False ao processar documentos reais
# com dados pessoais. O dataset do TCC (SROIE) é público.
REGISTRAR_CONTEUDO: bool = True

# --- OCR (Tesseract) --------------------------------------------------------
# Idioma padrão do Tesseract ('eng': o domínio do gabarito SROIE é recibo em
# inglês). Configurável por documento via campos.json ("idioma_ocr").
IDIOMA_OCR: str = "eng"

DIR_DADOS: Path = Path("dados")

# Documentos REAIS aprovados na validação humana (app). Cada configuração de
# campos guarda os seus numa subpasta própria (dados/aprovadas/<assinatura>/),
# como pares <id>.png + <id>.json (gabarito), no mesmo layout do dataset — assim
# a avaliação (M5, modo --aprovadas) pode rodar sobre eles no futuro.
DIR_APROVADAS: Path = DIR_DADOS / "aprovadas"

# --- Experimento SROIE (ICDAR 2019, Task 3) ----------------------------------
# Avaliação com ground truth EXTERNO (recibos reais em inglês; campos company,
# address, date e total). O DIRETÓRIO é a fonte única de verdade do split:
# só o trainval entra na base vetorial; o teste NUNCA é indexado (anti-leakage).
DIR_SROIE: Path = DIR_DADOS / "sroie"
DIR_SROIE_TRAINVAL: Path = DIR_SROIE / "trainval"
DIR_SROIE_TEST: Path = DIR_SROIE / "test"
DIR_SROIE_CACHE_OCR: Path = DIR_SROIE / "cache_ocr"

# Coleção Chroma EXCLUSIVA do experimento SROIE (separada da base do app).
NOME_COLECAO_SROIE: str = "sroie_trainval"

# Limiar de similaridade de edição normalizada (1 - Levenshtein/len_max) para
# considerar CORRETOS os campos textuais (company/address) vs o ground truth.
# Declarado na metodologia do relatório.
LIMIAR_SIMILARIDADE: float = 0.80

# Limiar (mais permissivo) para considerar um valor DERIVÁVEL do texto OCR de
# entrada — usado pela taxa de alucinação: um campo só é alucinação se está
# errado vs o ground truth E não é derivável/corrigível do OCR que o LLM viu.
LIMIAR_DERIVACAO: float = 0.70

# --- Campos a extrair (configuráveis pelo frontend) -------------------------
# Arquivo JSON com a lista de campos que o app espera extrair (editável pela
# tela de Configurações). Afeta SÓ o caminho de produção (app/CLI): a avaliação
# SROIE usa o schema FIXO (schema.ReciboSROIE), que é o experimento controlado
# do TCC. Criado automaticamente com os campos padrão (= ReciboSROIE) na 1ª
# execução.
CAMINHO_CAMPOS: str = "campos.json"

# Registro de VERSÕES da configuração de campos. Cada conjunto distinto de campos
# (topo + itens) recebe um número de versão estável (v1, v2, ...): mudar qualquer
# campo gera uma versão nova; voltar a uma configuração já vista reusa a versão
# dela. A versão identifica a base e os resultados — assim mudar campos NÃO afeta
# os resultados de versões anteriores. Criado/atualizado automaticamente.
CAMINHO_VERSOES: str = "campos_versoes.json"
