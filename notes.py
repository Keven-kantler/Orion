from datetime import datetime
from pathlib import Path

from config import PASTA_NOTES
from utils import normalizar_texto


_GATILHOS_ANOTACAO = (
    "cria uma anotacao dizendo",
    "criar uma anotacao dizendo",
    "cria anotacao dizendo",
    "criar anotacao dizendo",
    "anote que",
    "anota que",
)


def _extrair_conteudo_anotacao(texto):
    """
    Identifica o gatilho usando a versão normalizada, mas preserva o texto
    original da anotação sempre que possível.

    Assim:
        "Anote que Minha reunião é às 19h!"
    não vira:
        "minha reuniao e as 19h"
    """
    texto_original = str(texto or "").strip()

    if not texto_original:
        return ""

    texto_norm = normalizar_texto(texto_original)

    # Se commands.py já entregou apenas o conteúdo, não há gatilho para
    # remover e salvamos exatamente o que recebemos.
    gatilho_encontrado = None

    for gatilho in _GATILHOS_ANOTACAO:
        if gatilho in texto_norm:
            gatilho_encontrado = gatilho
            break

    if gatilho_encontrado is None:
        return texto_original

    # normalizar_texto pode remover acentos e sinais, portanto os índices da
    # string normalizada não são garantidamente iguais aos da original.
    # Procuramos primeiro variantes comuns diretamente no original.
    variantes = (
        "cria uma anotação dizendo",
        "criar uma anotação dizendo",
        "cria anotação dizendo",
        "criar anotação dizendo",
        "cria uma anotacao dizendo",
        "criar uma anotacao dizendo",
        "cria anotacao dizendo",
        "criar anotacao dizendo",
        "anote que",
        "anota que",
    )

    original_lower = texto_original.lower()

    for variante in variantes:
        indice = original_lower.find(variante)

        if indice >= 0:
            return texto_original[
                indice + len(variante):
            ].strip(" \t,;:-")

    # Fallback defensivo: se houve transformação que impediu alinhar o texto
    # original, usamos a extração normalizada em vez de salvar o comando todo.
    return texto_norm.split(
        gatilho_encontrado,
        1,
    )[1].strip()


def _novo_caminho_anotacao():
    """
    Cria um nome praticamente único.

    O arquivo antigo usava precisão de segundos; duas notas no mesmo segundo
    podiam apontar para o mesmo .txt e a segunda sobrescrevia a primeira.
    """
    pasta = Path(PASTA_NOTES)
    pasta.mkdir(
        parents=True,
        exist_ok=True,
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S_%f"
    )

    return pasta / f"nota_{timestamp}.txt"


def criar_anotacao(texto):
    conteudo = _extrair_conteudo_anotacao(
        texto
    )

    if not conteudo:
        return "O que você quer que eu anote?"

    caminho = _novo_caminho_anotacao()

    try:
        caminho.write_text(
            conteudo + "\n",
            encoding="utf-8",
        )
    except OSError as erro:
        print(
            f"Erro ao criar anotação {caminho}:",
            erro,
        )
        return "Não consegui criar a anotação."

    return "Anotação criada."


def ler_ultimas_anotacoes(quantidade=3):
    pasta = Path(PASTA_NOTES)

    if not pasta.is_dir():
        return "Ainda não encontrei anotações."

    try:
        quantidade = int(quantidade)
    except (TypeError, ValueError):
        quantidade = 3

    if quantidade <= 0:
        return "Ainda não encontrei anotações."

    try:
        arquivos = [
            caminho
            for caminho in pasta.iterdir()
            if (
                caminho.is_file()
                and caminho.suffix.lower() == ".txt"
            )
        ]
    except OSError as erro:
        print(
            f"Erro ao listar anotações em {pasta}:",
            erro,
        )
        return "Não consegui acessar as anotações."

    def _mtime_seguro(caminho):
        try:
            return caminho.stat().st_mtime
        except OSError:
            return 0.0

    arquivos.sort(
        key=_mtime_seguro,
        reverse=True,
    )

    if not arquivos:
        return "Ainda não encontrei anotações."

    trechos = []

    for caminho in arquivos[:quantidade]:
        try:
            conteudo = caminho.read_text(
                encoding="utf-8"
            ).strip()
        except (OSError, UnicodeError) as erro:
            print(
                f"Erro ao ler anotação {caminho}:",
                erro,
            )
            continue

        if conteudo:
            trechos.append(
                conteudo[:120]
            )

    if not trechos:
        return "As últimas anotações estão vazias."

    return (
        "Últimas anotações: "
        + " | ".join(trechos)
    )