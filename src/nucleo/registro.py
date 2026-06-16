"""
Banco de RESULTADOS (SQLite) — histórico de todas as extrações.
================================================================
Complementa o banco vetorial (que guarda SÓ pares validados, para a recuperação
do RAG): aqui fica o registro de CADA extração executada — aprovada, rejeitada
ou pendente — com o documento de origem, o JSON gerado, o timestamp, o status
da validação humana e a VERSÃO do pipeline que a produziu (rastreabilidade).

Tecnologia: SQLite via stdlib (`sqlite3`), arquivo único (config.CAMINHO_REGISTRO),
sem ORM — coerente com a regra "sem over-engineering" do projeto.

Privacidade: com config.REGISTRAR_CONTEUDO = False, texto OCR e JSON extraído
NÃO são gravados (somente metadados) — para documentos reais com dados pessoais.
"""

import sqlite3
import uuid
from datetime import datetime, timezone
from typing import Optional

from nucleo.config import CAMINHO_REGISTRO, PIPELINE_VERSAO, REGISTRAR_CONTEUDO

STATUS_VALIDOS = ("pendente", "aprovado", "rejeitado")

_SQL_CRIAR = """
CREATE TABLE IF NOT EXISTS extracoes (
    id               TEXT PRIMARY KEY,
    criado_em        TEXT NOT NULL,             -- ISO-8601 UTC
    documento_origem TEXT NOT NULL,             -- caminho/ID do documento
    texto_ocr        TEXT,                      -- NULL se REGISTRAR_CONTEUDO=False
    json_extraido    TEXT,                      -- saída do LLM (mesmo se inválida)
    json_valido      INTEGER NOT NULL,          -- 0/1 (parse + Pydantic)
    valido_primeira  INTEGER,                   -- 0/1: validou já na 1ª tentativa
    n_tentativas     INTEGER,
    status_validacao TEXT NOT NULL DEFAULT 'pendente',  -- pendente|aprovado|rejeitado
    validado_em      TEXT,                      -- timestamp da decisão humana
    versao_pipeline  TEXT NOT NULL,
    provedor         TEXT,
    modelo           TEXT,
    use_rag          INTEGER NOT NULL,
    k_exemplos       INTEGER,                   -- nº de exemplos recuperados
    versao_campos    INTEGER,                   -- versão da config de campos (app)
    experimento      TEXT,                      -- 'app' | 'cli' | 'sroie'
    duracao_ocr_s    REAL,
    duracao_llm_s    REAL,
    duracao_total_s  REAL,
    tokens_entrada   INTEGER,
    tokens_saida     INTEGER,
    custo_usd        REAL
);
"""


def _agora() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def conectar(caminho: str = CAMINHO_REGISTRO) -> sqlite3.Connection:
    """Abre (e inicializa, se preciso) o banco de resultados."""
    con = sqlite3.connect(caminho)
    con.execute(_SQL_CRIAR)
    con.commit()
    return con


def registrar_extracao(
    documento_origem: str,
    texto_ocr: Optional[str],
    json_extraido: Optional[str],
    json_valido: bool,
    use_rag: bool,
    provedor: Optional[str] = None,
    modelo: Optional[str] = None,
    valido_primeira: Optional[bool] = None,
    n_tentativas: Optional[int] = None,
    k_exemplos: Optional[int] = None,
    versao_campos: Optional[int] = None,
    experimento: Optional[str] = None,
    duracao_ocr_s: Optional[float] = None,
    duracao_llm_s: Optional[float] = None,
    duracao_total_s: Optional[float] = None,
    tokens_entrada: Optional[int] = None,
    tokens_saida: Optional[int] = None,
    custo_usd: Optional[float] = None,
    caminho_banco: str = CAMINHO_REGISTRO,
) -> str:
    """Insere uma extração com status 'pendente' e devolve o id gerado.

    O conteúdo (OCR + JSON) só é gravado se config.REGISTRAR_CONTEUDO permitir."""
    id_ = str(uuid.uuid4())
    con = conectar(caminho_banco)
    try:
        con.execute(
            """INSERT INTO extracoes (
                   id, criado_em, documento_origem, texto_ocr, json_extraido,
                   json_valido, valido_primeira, n_tentativas, status_validacao,
                   versao_pipeline, provedor, modelo, use_rag, k_exemplos,
                   versao_campos, experimento, duracao_ocr_s, duracao_llm_s,
                   duracao_total_s, tokens_entrada, tokens_saida, custo_usd
               ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                id_,
                _agora(),
                documento_origem,
                texto_ocr if REGISTRAR_CONTEUDO else None,
                json_extraido if REGISTRAR_CONTEUDO else None,
                int(json_valido),
                None if valido_primeira is None else int(valido_primeira),
                n_tentativas,
                "pendente",
                PIPELINE_VERSAO,
                provedor,
                modelo,
                int(use_rag),
                k_exemplos,
                versao_campos,
                experimento,
                duracao_ocr_s,
                duracao_llm_s,
                duracao_total_s,
                tokens_entrada,
                tokens_saida,
                custo_usd,
            ),
        )
        con.commit()
    finally:
        con.close()
    return id_


def registrar_resultado(
    resultado,
    documento_origem: str,
    use_rag: bool,
    provedor: Optional[str],
    modelo: Optional[str],
    experimento: str,
    versao_campos: Optional[int] = None,
    custo_usd: Optional[float] = None,
    caminho_banco: str = CAMINHO_REGISTRO,
) -> str:
    """Registra um `pipeline.ResultadoExtracao` (duck-typed para não acoplar
    este módulo ao pipeline) e devolve o id. É o caminho usado por CLI, app e
    harnesses — um único lugar mapeia o resultado para as colunas da tabela.

    `custo_usd` não informado é ESTIMADO aqui a partir do provedor/tokens
    (0.0 para Ollama local; None se o preço do modelo não está cadastrado)."""
    if custo_usd is None and provedor:
        custo_usd = custo_estimado(
            provedor, modelo, resultado.tokens_entrada, resultado.tokens_saida
        )
    return registrar_extracao(
        documento_origem=documento_origem,
        texto_ocr=resultado.texto_ocr,
        json_extraido=resultado.json_bruto,
        json_valido=resultado.nota is not None,
        use_rag=use_rag,
        provedor=provedor,
        modelo=modelo,
        valido_primeira=resultado.valido_primeira,
        n_tentativas=resultado.n_tentativas,
        k_exemplos=resultado.k_exemplos,
        versao_campos=versao_campos,
        experimento=experimento,
        duracao_ocr_s=resultado.duracao_ocr_s,
        duracao_llm_s=resultado.duracao_llm_s,
        duracao_total_s=resultado.duracao_total_s,
        tokens_entrada=resultado.tokens_entrada,
        tokens_saida=resultado.tokens_saida,
        custo_usd=custo_usd,
        caminho_banco=caminho_banco,
    )


def atualizar_status(
    id_extracao: str,
    status: str,
    json_final: Optional[str] = None,
    caminho_banco: str = CAMINHO_REGISTRO,
) -> None:
    """Registra a decisão humana (aprovado/rejeitado). Se o operador corrigiu o
    JSON antes de aprovar, `json_final` substitui o extraído (auditável pelo
    timestamp `validado_em`)."""
    if status not in STATUS_VALIDOS:
        raise ValueError(f"Status inválido: {status!r} (use {STATUS_VALIDOS})")
    con = conectar(caminho_banco)
    try:
        if json_final is not None and REGISTRAR_CONTEUDO:
            con.execute(
                "UPDATE extracoes SET status_validacao=?, validado_em=?, json_extraido=? WHERE id=?",
                (status, _agora(), json_final, id_extracao),
            )
        else:
            con.execute(
                "UPDATE extracoes SET status_validacao=?, validado_em=? WHERE id=?",
                (status, _agora(), id_extracao),
            )
        con.commit()
    finally:
        con.close()


def carregar_extracoes(
    limite: Optional[int] = None, caminho_banco: str = CAMINHO_REGISTRO
) -> list:
    """Extrações registradas, da mais recente para a mais antiga, como dicts.
    Alimenta o Dashboard do frontend (contagens, tabela e gráficos)."""
    con = conectar(caminho_banco)
    con.row_factory = lambda cursor, linha: {
        d[0]: linha[i] for i, d in enumerate(cursor.description)
    }
    try:
        sql = "SELECT * FROM extracoes ORDER BY criado_em DESC"
        if limite:
            sql += f" LIMIT {int(limite)}"
        return con.execute(sql).fetchall()
    finally:
        con.close()


def medias_por_condicao(
    experimento: Optional[str] = None, caminho_banco: str = CAMINHO_REGISTRO
) -> list:
    """Médias de tempo/tokens por condição (COM/SEM RAG), sobre o histórico do
    banco de resultados. Uma linha por condição:
    {condicao, n, duracao_llm_s, tokens_entrada, tokens_saida}.
    Usada pelo Dashboard e pela página de Validação (contexto ao vivo)."""
    con = conectar(caminho_banco)
    try:
        sql = (
            "SELECT use_rag, COUNT(*), AVG(duracao_llm_s), "
            "AVG(tokens_entrada), AVG(tokens_saida) FROM extracoes"
        )
        parametros: tuple = ()
        if experimento:
            sql += " WHERE experimento = ?"
            parametros = (experimento,)
        sql += " GROUP BY use_rag ORDER BY use_rag"
        return [
            {
                "condicao": "COM RAG" if use_rag else "SEM RAG",
                "n": n,
                "duracao_llm_s": round(llm, 1) if llm is not None else None,
                "tokens_entrada": round(tok_e, 1) if tok_e is not None else None,
                "tokens_saida": round(tok_s, 1) if tok_s is not None else None,
            }
            for use_rag, n, llm, tok_e, tok_s in con.execute(sql, parametros)
        ]
    finally:
        con.close()


# ---------------------------------------------------------------------------
# Custo por documento (métrica secundária da avaliação).
# Ollama roda local: custo monetário 0 (os tokens ficam registrados mesmo
# assim). Para provedores pagos, preencher a tabela US$/1M tokens (conferir a
# tabela de preços vigente antes de reportar custo no relatório).
# ---------------------------------------------------------------------------
PRECO_POR_MILHAO = {
    # provedor: {modelo: (entrada, saida)} em US$ por 1M tokens
    "ollama": {},  # local => 0
}


def custo_estimado(
    provedor: str, modelo: str, tokens_entrada: Optional[int], tokens_saida: Optional[int]
) -> Optional[float]:
    """Custo estimado em US$. 0.0 para Ollama (local); None se o preço do
    modelo não estiver cadastrado (melhor não reportar do que reportar errado)."""
    if provedor == "ollama":
        return 0.0
    precos = PRECO_POR_MILHAO.get(provedor, {}).get(modelo)
    if precos is None or tokens_entrada is None or tokens_saida is None:
        return None
    return (tokens_entrada * precos[0] + tokens_saida * precos[1]) / 1_000_000
