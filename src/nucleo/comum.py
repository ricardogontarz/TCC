"""
Utilitários compartilhados pelo harness de avaliação (SROIE).
============================================================================
Infraestrutura pura, sem regra de negócio nem definição de métrica — as
métricas vivem em `metricas.py`
(avaliação externa). Centralizar aqui evita as cópias divergirem.
"""

import re
import time
from pathlib import Path
from typing import Callable, List, Sequence, Tuple, TypeVar

from google.api_core.exceptions import ResourceExhausted

T = TypeVar("T")


def slug_modelo(provedor: str, modelo: str) -> str:
    """Transforma 'ollama' + 'llama3.1:8b' num nome de arquivo seguro:
    'ollama-llama3-1-8b'. Usado para separar as saídas por modelo."""
    bruto = f"{provedor}_{modelo}".lower()
    return re.sub(r"[^a-z0-9]+", "-", bruto).strip("-")


def listar_pares(
    diretorio: Path, extensoes: Sequence[str] = ("png", "jpg")
) -> List[Tuple[Path, Path]]:
    """Pares (imagem, gabarito JSON) de um diretório, ordenados por nome
    (determinístico). Imagens sem .json correspondente são ignoradas."""
    imagens = sorted(
        imagem for ext in extensoes for imagem in diretorio.glob(f"*.{ext}")
    )
    pares = []
    for imagem in imagens:
        gabarito = imagem.with_suffix(".json")
        if gabarito.exists():
            pares.append((imagem, gabarito))
    return pares


def tolerar_rate_limit(
    chamada: Callable[[], T],
    rotulo: str = "",
    espera: float = 35.0,
    max_tentativas: int = 4,
) -> T:
    """Executa `chamada` tolerando o rate-limit do free tier do Gemini (429,
    que reseta em <60s): espera e re-tenta. Com Ollama (local) nunca dispara.
    Garante que todas as notas sejam medidas mesmo numa conta gratuita."""
    for tentativa in range(1, max_tentativas + 1):
        try:
            return chamada()
        except ResourceExhausted:
            if tentativa == max_tentativas:
                raise
            print(f"  [rate-limit] {rotulo}: aguardando {espera:.0f}s e tentando de novo...")
            time.sleep(espera)
