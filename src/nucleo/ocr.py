"""
M1 — OCR (Tesseract) com pré-processamento de imagem.
=====================================================
Cumpre parte do Objetivo 1 da proposta: extrair o texto bruto da nota fiscal.
O pré-processamento (cinza + binarização Otsu) costuma render mais acurácia em
notas fiscais (fundo com ruído, fonte pequena) do que trocar de LLM depois.

A entrada é uma IMAGEM (PNG/JPG). Se você tiver um PDF, converta para imagem
antes (pdf2image/PyMuPDF) — o gerador de dataset (M0) já entrega PNG pronto.
"""

from typing import Optional

import cv2
import pytesseract

from nucleo.config import IDIOMA_OCR


def preprocessar_imagem(caminho: str):
    """Carrega a imagem, converte para tons de cinza e binariza com Otsu."""
    imagem = cv2.imread(caminho)
    if imagem is None:
        raise FileNotFoundError(f"Não consegui abrir a imagem: {caminho}")
    cinza = cv2.cvtColor(imagem, cv2.COLOR_BGR2GRAY)
    _, binarizada = cv2.threshold(
        cinza, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU
    )
    return binarizada


def ocr_extrair_texto(caminho: str, idioma: Optional[str] = None) -> str:
    """Roda o Tesseract sobre a imagem pré-processada e devolve o texto.

    `idioma`: código de língua do Tesseract. Default (None) usa o do config
    ("por" — notas fiscais). O experimento SROIE passa "eng" (recibos em inglês)."""
    imagem = preprocessar_imagem(caminho)
    texto = pytesseract.image_to_string(imagem, lang=idioma or IDIOMA_OCR)
    return texto.strip()
