"""
M2 — Banco vetorial (ChromaDB) indexando pares OCR -> JSON validado.
====================================================================
Cumpre o Objetivo 2 da proposta. Cada par (texto OCR, JSON aprovado por humano)
é vetorizado e guardado. Na inferência, recuperamos os exemplos mais parecidos
para montar o prompt few-shot — é o "R" do RAG.

Todos os parâmetros sensíveis (caminho, collection, modelo de embedding) vêm de
config.py, garantindo consistência entre gravação, avaliação e frontend.
"""

import uuid
from typing import List, Optional

import chromadb
from chromadb.utils import embedding_functions

from nucleo.config import CAMINHO_CHROMA, MODELO_EMBEDDING


class BancoVetorial:
    def __init__(
        self,
        nome_colecao: str,
        caminho: str = CAMINHO_CHROMA,
        modelo_embedding: str = MODELO_EMBEDDING,
    ):
        self.cliente = chromadb.PersistentClient(path=caminho)
        funcao_embedding = embedding_functions.SentenceTransformerEmbeddingFunction(
            model_name=modelo_embedding
        )
        self.colecao = self.cliente.get_or_create_collection(
            name=nome_colecao, embedding_function=funcao_embedding
        )

    def contar(self) -> int:
        """Quantos pares validados há na base. Usado pelo frontend para mostrar
        o crescimento da base (evidência da realimentação do Objetivo 3)."""
        return self.colecao.count()

    def buscar(
        self, texto_ocr: str, k: int = 3, excluir_texto: Optional[str] = None
    ) -> List[dict]:
        """Recupera os k exemplos validados mais parecidos. Trata o cold start:
        com a base vazia, devolve [] e o pipeline cai em LLM puro (sem RAG).

        `excluir_texto`: descarta resultados cujo OCR é exatamente igual a este
        texto. Serve ao leave-one-out da avaliação sobre os APROVADOS — a nota
        que está sendo avaliada não pode se recuperar a si mesma (vazamento)."""
        total = self.colecao.count()
        if total == 0:
            return []
        # Quando vamos excluir a própria nota, pedimos 1 a mais para repor.
        n = min(k + (1 if excluir_texto is not None else 0), total)
        resultado = self.colecao.query(query_texts=[texto_ocr], n_results=n)
        exemplos = []
        for doc, meta in zip(resultado["documents"][0], resultado["metadatas"][0]):
            if excluir_texto is not None and doc == excluir_texto:
                continue  # leave-one-out: ignora a própria nota
            exemplos.append({"ocr": doc, "json": meta["json"]})
        return exemplos[:k]

    def adicionar(
        self, texto_ocr: str, json_validado: str, metadados: Optional[dict] = None
    ) -> None:
        """Grava um par aprovado pelo humano. É o que faz a base melhorar a cada
        nota processada (realimentação do Objetivo 3).

        `metadados`: chaves extras de rastreabilidade (ex.: doc_id e split no
        experimento SROIE — base da auditoria anti-leakage)."""
        meta = {"json": json_validado}
        if metadados:
            meta.update(metadados)
        self.colecao.add(
            documents=[texto_ocr],
            metadatas=[meta],
            ids=[str(uuid.uuid4())],
        )
