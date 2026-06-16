"""
Métricas da avaliação externa (SROIE) — núcleo metodológico, puro e testável.
=============================================================================
Tudo aqui é função pura (sem I/O, sem LLM), para que cada definição possa ser
testada de forma isolada e citada na metodologia do relatório.

Definições (declaradas no relatório):

- **Correto**: campo previsto não-nulo que casa com o ground truth do SROIE.
  O casamento depende do TIPO: data comparada como data normalizada; total como
  número (tolerância de 1 centavo); company/address por similaridade de edição
  normalizada >= config.LIMIAR_SIMILARIDADE.
- **Precisão/Recall/F1 por campo**: TP = previsto e correto; FP = previsto e
  incorreto (inclui prever valor onde o gabarito é nulo); FN = gabarito não-nulo
  sem previsão correta. Um valor errado conta como FP e FN (padrão em KIE).
- **Alucinação (métrica principal)**: campo previsto não-nulo que está ERRADO
  em relação ao ground truth E cujo valor NÃO é derivável do texto OCR que o
  LLM recebeu. Correções legítimas de ruído de OCR (ex.: "4,9S" -> 4.95) não
  contam como alucinação — contam como ERRO DE EXTRAÇÃO se divergirem do
  gabarito. Derivabilidade textual usa um limiar mais permissivo
  (config.LIMIAR_DERIVACAO), por janela deslizante sobre o OCR.
- **Exact match do documento**: todos os campos simultaneamente corretos
  (campos nulos no gabarito exigem previsão nula).
- **Validade do JSON**: parse + Pydantic (medida no pipeline, agregada aqui).
"""

import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from nucleo.config import LIMIAR_DERIVACAO, LIMIAR_SIMILARIDADE

TOLERANCIA_NUMERO = 0.01  # 1 centavo

# ============================================================================
# Normalização por tipo
# ============================================================================


def normalizar_texto(valor) -> Optional[str]:
    """Minúsculas + espaços colapsados. None/vazio -> None."""
    if valor is None:
        return None
    s = re.sub(r"\s+", " ", str(valor)).strip().lower()
    return s or None


def normalizar_numero(valor) -> Optional[float]:
    """Aceita float ou string com símbolo de moeda ('RM 1,234.56', 'R$ 9,00').
    Decide o separador decimal pela ÚLTIMA pontuação da string."""
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return round(float(valor), 2)
    s = re.sub(r"[^\d.,\-]", "", str(valor))
    if not s:
        return None
    # Se tem ',' e '.', o que aparece por último é o decimal.
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        # Só vírgula: decimal se houver 1-2 dígitos depois dela (9,00); senão milhar.
        inteiro, _, resto = s.rpartition(",")
        if len(resto) in (1, 2):
            s = inteiro.replace(",", "") + "." + resto
        else:
            s = s.replace(",", "")
    try:
        return round(float(s), 2)
    except ValueError:
        return None


_MESES_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "sept": 9, "oct": 10, "nov": 11, "dec": 12,
}


def normalizar_data(valor) -> Optional[str]:
    """Normaliza datas dos formatos comuns no SROIE para ISO aaaa-mm-dd.
    Formatos: dd/mm/aaaa, dd-mm-aa, dd.mm.aaaa, aaaa-mm-dd, aaaammdd,
    'dd MON aaaa' (meses em inglês). Irreconhecível -> devolve o texto cru
    normalizado (a comparação cai para igualdade de string)."""
    if valor is None:
        return None
    s = str(valor).strip()
    if not s:
        return None

    # dd/mm/aaaa | dd-mm-aa | dd.mm.aaaa etc.
    m = re.search(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\b", s)
    if m:
        dia, mes, ano = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if ano < 100:
            ano += 2000
        try:
            return datetime(ano, mes, dia).date().isoformat()
        except ValueError:
            pass

    # aaaa-mm-dd (ISO)
    m = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            pass

    # aaaammdd (8 dígitos colados)
    m = re.fullmatch(r"(\d{4})(\d{2})(\d{2})", s)
    if m:
        try:
            return datetime(int(m.group(1)), int(m.group(2)), int(m.group(3))).date().isoformat()
        except ValueError:
            pass

    # dd MON aaaa (inglês: '27 MAR 2018', '5 March 2018')
    m = re.search(r"\b(\d{1,2})\s+([A-Za-z]{3,9})\.?\s+(\d{2,4})\b", s)
    if m:
        mes = _MESES_EN.get(m.group(2)[:4].lower().rstrip("."), _MESES_EN.get(m.group(2)[:3].lower()))
        if mes:
            ano = int(m.group(3))
            if ano < 100:
                ano += 2000
            try:
                return datetime(ano, mes, int(m.group(1))).date().isoformat()
            except ValueError:
                pass

    return normalizar_texto(s)  # fallback: igualdade textual


# ============================================================================
# Similaridade de edição (Levenshtein normalizada)
# ============================================================================


def distancia_levenshtein(a: str, b: str) -> int:
    """Distância de edição clássica (inserção/remoção/substituição), DP O(n*m)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    anterior = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        atual = [i]
        for j, cb in enumerate(b, 1):
            atual.append(min(
                anterior[j] + 1,        # remoção
                atual[j - 1] + 1,       # inserção
                anterior[j - 1] + (ca != cb),  # substituição
            ))
        anterior = atual
    return anterior[-1]


def similaridade(a: Optional[str], b: Optional[str]) -> float:
    """Similaridade de edição normalizada: 1 - dist/len_max, em [0, 1]."""
    a, b = a or "", b or ""
    if not a and not b:
        return 1.0
    maior = max(len(a), len(b))
    return 1.0 - distancia_levenshtein(a, b) / maior


# ============================================================================
# Casamento previsto x gabarito (define "correto")
# ============================================================================


def campo_correto(tipo: str, previsto, gabarito, limiar: float = LIMIAR_SIMILARIDADE) -> bool:
    """O campo previsto casa com o ground truth? (ambos não-nulos)
    - data: igualdade após normalização para ISO;
    - numero: |a - b| <= 1 centavo;
    - texto: similaridade de edição normalizada >= limiar (declarado)."""
    if previsto is None or gabarito is None:
        return False
    if tipo == "data":
        return normalizar_data(previsto) == normalizar_data(gabarito)
    if tipo == "numero":
        a, b = normalizar_numero(previsto), normalizar_numero(gabarito)
        if a is None or b is None:
            return False
        return abs(a - b) <= TOLERANCIA_NUMERO
    return similaridade(normalizar_texto(previsto), normalizar_texto(gabarito)) >= limiar


# ============================================================================
# Derivabilidade do OCR (separa alucinação de correção legítima)
# ============================================================================


def _so_digitos(texto) -> str:
    return re.sub(r"\D", "", str(texto or ""))


def _melhor_janela(alvo: str, texto: str) -> float:
    """Maior similaridade entre `alvo` e janelas deslizantes de `texto` com
    comprimento próximo ao do alvo. Usada para decidir se um valor textual é
    derivável do OCR mesmo com ruído de reconhecimento."""
    if not alvo:
        return 0.0
    if alvo in texto:
        return 1.0
    n, m = len(texto), len(alvo)
    if n <= m:
        return similaridade(alvo, texto)
    passo = max(1, m // 4)
    melhor = 0.0
    # Janela 20% maior que o alvo absorve inserções do OCR (espaços, lixo).
    largura = min(n, int(m * 1.2) + 1)
    for inicio in range(0, n - m + 1, passo):
        melhor = max(melhor, similaridade(alvo, texto[inicio:inicio + largura]))
        if melhor == 1.0:
            break
    return melhor


def derivavel_do_ocr(tipo: str, valor, texto_ocr: str, limiar: float = LIMIAR_DERIVACAO) -> bool:
    """O valor previsto pode ser derivado/corrigido a partir do texto OCR que o
    LLM recebeu? Se NÃO, e o valor também está errado vs o gabarito, é alucinação.

    - numero: a sequência de dígitos (com e sem casas decimais) aparece no
      fluxo de dígitos do OCR — robusto a 'RM', '.', ',';
    - data: alguma representação comum da data (dd/mm/aaaa, dd-mm-aa, ISO,
      dd MON aaaa...) aparece no OCR, ou a sequência de dígitos aparece;
    - texto: melhor janela deslizante do OCR com similaridade >= limiar
      (mais permissivo que o limiar de acerto, de propósito: ruído de OCR)."""
    if valor is None:
        return True  # nada previsto -> nada a derivar
    ocr_norm = normalizar_texto(texto_ocr) or ""
    ocr_digitos = _so_digitos(texto_ocr)

    if tipo == "numero":
        v = normalizar_numero(valor)
        if v is None:
            return False
        if _so_digitos(f"{v:.2f}") in ocr_digitos:
            return True
        # Valor inteiro impresso sem casas decimais ('RM60').
        return v == int(v) and str(int(v)) in ocr_digitos

    if tipo == "data":
        iso = normalizar_data(valor)
        if not iso or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", iso):
            return False
        ano, mes, dia = iso.split("-")
        ano2 = ano[2:]
        representacoes = [
            f"{dia}/{mes}/{ano}", f"{dia}-{mes}-{ano}", f"{dia}.{mes}.{ano}",
            f"{dia}/{mes}/{ano2}", f"{dia}-{mes}-{ano2}", f"{dia}.{mes}.{ano2}",
            iso, f"{ano}{mes}{dia}", f"{dia}{mes}{ano}",
            f"{int(dia)}/{int(mes)}/{ano}",  # sem zeros à esquerda
        ]
        if any(r.lower() in ocr_norm for r in representacoes):
            return True
        # 'dd MON aaaa' (inglês)
        abrev = [k for k, v in _MESES_EN.items() if v == int(mes)]
        return any(
            re.search(rf"\b0?{int(dia)}\s*{ab}\w*\s*{ano}\b", ocr_norm) for ab in abrev
        )

    alvo = normalizar_texto(valor)
    if not alvo:
        return False
    return _melhor_janela(alvo, ocr_norm) >= limiar


# ============================================================================
# Avaliação de um documento e agregação
# ============================================================================


def avaliar_documento(
    previsto: dict,
    gabarito: dict,
    texto_ocr: str,
    campos: List[Tuple[str, str]],
    limiar_match: float = LIMIAR_SIMILARIDADE,
    limiar_derivacao: float = LIMIAR_DERIVACAO,
) -> dict:
    """Compara um documento previsto com o ground truth.

    `campos`: lista de (nome, tipo) — para o SROIE:
    [("company","texto"), ("address","texto"), ("date","data"), ("total","numero")].

    Devolve, por campo: tp/fp/fn, alucinacao, erro_grounded; e o exact match
    do documento. O gabarito vem SEMPRE do dataset — nunca do modelo."""
    por_campo: Dict[str, dict] = {}
    doc_exato = True
    for nome, tipo in campos:
        prev = previsto.get(nome)
        gab = gabarito.get(nome)
        correto = campo_correto(tipo, prev, gab, limiar_match)
        tp = int(correto)
        fp = int(prev is not None and not correto)
        fn = int(gab is not None and not correto)
        alucinacao = 0
        erro_grounded = 0
        if prev is not None and not correto:
            if derivavel_do_ocr(tipo, prev, texto_ocr, limiar_derivacao):
                erro_grounded = 1
            else:
                alucinacao = 1
        if not (correto or (prev is None and gab is None)):
            doc_exato = False
        por_campo[nome] = {
            "tp": tp, "fp": fp, "fn": fn,
            "previsto_nao_nulo": int(prev is not None),
            "alucinacao": alucinacao,
            "erro_grounded": erro_grounded,
        }
    return {"campos": por_campo, "exact_match_doc": int(doc_exato)}


def _prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
    precisao = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * precisao * recall / (precisao + recall) if (precisao + recall) else 0.0
    return precisao, recall, f1


def agregar(avaliacoes: List[dict], campos: List[Tuple[str, str]]) -> dict:
    """Agrega as avaliações por documento em métricas finais.

    Devolve: por campo {precisao, recall, f1, tp, fp, fn}; micro-média geral;
    taxa_alucinacao e taxa_erro_grounded (denominador: campos previstos
    não-nulos); exact_match_doc (fração de documentos 100% corretos)."""
    nomes = [n for n, _ in campos]
    soma = {n: {"tp": 0, "fp": 0, "fn": 0, "prev": 0, "aluc": 0, "erro": 0} for n in nomes}
    docs_exatos = 0
    for av in avaliacoes:
        docs_exatos += av["exact_match_doc"]
        for n in nomes:
            c = av["campos"][n]
            soma[n]["tp"] += c["tp"]
            soma[n]["fp"] += c["fp"]
            soma[n]["fn"] += c["fn"]
            soma[n]["prev"] += c["previsto_nao_nulo"]
            soma[n]["aluc"] += c["alucinacao"]
            soma[n]["erro"] += c["erro_grounded"]

    por_campo = {}
    for n in nomes:
        p, r, f1 = _prf(soma[n]["tp"], soma[n]["fp"], soma[n]["fn"])
        por_campo[n] = {
            "precisao": p, "recall": r, "f1": f1,
            "tp": soma[n]["tp"], "fp": soma[n]["fp"], "fn": soma[n]["fn"],
        }

    tp = sum(soma[n]["tp"] for n in nomes)
    fp = sum(soma[n]["fp"] for n in nomes)
    fn = sum(soma[n]["fn"] for n in nomes)
    prev = sum(soma[n]["prev"] for n in nomes)
    aluc = sum(soma[n]["aluc"] for n in nomes)
    erro = sum(soma[n]["erro"] for n in nomes)
    p, r, f1 = _prf(tp, fp, fn)

    n_docs = len(avaliacoes)
    return {
        "por_campo": por_campo,
        "micro": {"precisao": p, "recall": r, "f1": f1, "tp": tp, "fp": fp, "fn": fn},
        "taxa_alucinacao": aluc / prev if prev else 0.0,
        "taxa_erro_grounded": erro / prev if prev else 0.0,
        "previstos_nao_nulos": prev,
        "exact_match_doc": docs_exatos / n_docs if n_docs else 0.0,
        "n_documentos": n_docs,
    }
