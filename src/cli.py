"""
CLI — ponto de entrada para extrair um documento e (opcionalmente) validá-lo.
=============================================================================
Orquestra os módulos: OCR -> RAG -> LLM -> validação Pydantic -> (validação humana).
Usa a MESMA configuração de campos do app (campos.json): por padrão, os campos
do gabarito SROIE (company/address/date/total) e a coleção da versão atual.

Exemplos de uso:
  python src/cli.py --imagem dados/sroie/test/X51005365187.jpg
  python src/cli.py --imagem recibo.png --sem-rag      # baseline (Obj 4)
  python src/cli.py --imagem recibo.png --validar      # abre o M4
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from nucleo import campos as campos_mod  # noqa: E402
from nucleo import registro  # noqa: E402
from nucleo.banco_vetorial import BancoVetorial  # noqa: E402
from nucleo.config import MODELO_LLM, MODELO_OLLAMA, PROVEDOR_LLM  # noqa: E402
from nucleo.pipeline import extrair  # noqa: E402
from nucleo.schema_dinamico import construir_modelo  # noqa: E402
from validacao import validacao_humana  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pipeline RAG + OCR -> JSON para documentos (recibos/notas)."
    )
    parser.add_argument("--imagem", required=True, help="Caminho da imagem do documento.")
    parser.add_argument(
        "--sem-rag",
        action="store_true",
        help="Desliga a recuperação (modo baseline para o Objetivo 4).",
    )
    parser.add_argument(
        "--validar",
        action="store_true",
        help="Abre a etapa de validação humana após a extração.",
    )
    parser.add_argument(
        "--provedor",
        choices=["ollama", "gemini"],
        default=None,
        help="Sobrescreve o provedor de LLM do config (ollama/gemini).",
    )
    parser.add_argument(
        "--modelo",
        default=None,
        help="Sobrescreve o nome do modelo do provedor escolhido.",
    )
    args = parser.parse_args()

    # Mesma fonte de campos do app: schema dinâmico + coleção por versão.
    cfg = campos_mod.carregar_config()
    Modelo = construir_modelo(cfg)
    banco = BancoVetorial(nome_colecao=campos_mod.nome_colecao_para(cfg))
    resultado = extrair(
        args.imagem,
        banco,
        use_rag=not args.sem_rag,
        retornar_metadados=True,
        provedor=args.provedor,
        modelo=args.modelo,
        modelo_schema=Modelo,
        idioma_ocr=cfg.get("idioma_ocr"),
    )
    if resultado.nota is None:
        raise SystemExit(f"Não foi possível obter um JSON válido: {resultado.erro}")
    texto_ocr, dados = resultado.texto_ocr, resultado.nota

    # Toda extração entra no banco de RESULTADOS como 'pendente'; a validação
    # humana (--validar) atualiza para aprovado/rejeitado.
    provedor = args.provedor or PROVEDOR_LLM
    resultado.registro_id = registro.registrar_resultado(
        resultado,
        documento_origem=args.imagem,
        use_rag=not args.sem_rag,
        provedor=provedor,
        modelo=args.modelo or (MODELO_OLLAMA if provedor == "ollama" else MODELO_LLM),
        experimento="cli",
        versao_campos=campos_mod.versao_dos_campos(cfg),
    )

    print("\n--- TEXTO OCR (Tesseract) ---")
    print(texto_ocr)
    print("\n--- JSON ESTRUTURADO ---")
    print(dados.model_dump_json(indent=2))

    if args.validar:
        validacao_humana(texto_ocr, dados, banco, registro_id=resultado.registro_id)


if __name__ == "__main__":
    main()
