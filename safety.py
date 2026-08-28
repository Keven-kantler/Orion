import re

from utils import normalizar_texto


_MARCADORES_PERGUNTA = (
    "como ",
    "por que ",
    "porque ",
    "o que ",
    "qual ",
    "quais ",
    "quando ",
    "onde ",
    "quem ",
    "posso ",
    "pode ",
    "da para ",
    "e possivel ",
    "me explica ",
    "me explique ",
)

_MARCADORES_NEGACAO = (
    "nao ",
    "nunca ",
    "jamais ",
)


_PADROES_ACAO_PERIGOSA = (
    # Energia / sessão
    r"\b(?:desliga|desligue|desligar)\s+(?:o\s+)?(?:pc|computador|windows)\b",
    r"\b(?:reinicia|reinicie|reiniciar)\s+(?:o\s+)?(?:pc|computador|windows)\b",

    # Fechamento forçado
    r"\b(?:fecha|feche|fechar|encerra|encerre|encerrar|mata|mate|matar)\s+"
    r"(?:o\s+|a\s+)?(?:programa|processo|aplicativo|app)\b",

    # Exclusão de arquivos/pastas
    r"\b(?:deleta|delete|deletar|apaga|apague|apagar|remove|remova|remover)\s+"
    r"(?:o\s+|a\s+|os\s+|as\s+)?(?:arquivo|arquivos|pasta|pastas|diretorio|diretorios)\b",

    # Execução arbitrária
    r"\b(?:executa|execute|executar|roda|rode|rodar)\s+"
    r"(?:o\s+|um\s+|esse\s+|este\s+)?(?:comando|script|powershell|cmd)\b",

    r"\b(?:abre|abra|abrir)\s+(?:o\s+)?(?:terminal|powershell|cmd)\s+"
    r"(?:e\s+)?(?:executa|execute|roda|rode)\b",
)


def _parece_pergunta_ou_explicacao(texto_norm):
    """
    Evita confundir menção/discussão com pedido de execução.

    Exemplos que NÃO devem ser tratados como ação:
        "como reiniciar o pc?"
        "me explica como apagar um arquivo"
        "posso desligar o computador?"
    """
    if not texto_norm:
        return False

    if texto_norm.endswith("?"):
        return True

    return texto_norm.startswith(
        _MARCADORES_PERGUNTA
    )


def _parece_negacao(texto_norm):
    """
    "não desligue o pc" não é uma solicitação para executar a ação.
    """
    return texto_norm.startswith(
        _MARCADORES_NEGACAO
    )


def acao_perigosa(texto):
    """
    Retorna True somente para pedidos que parecem solicitar diretamente
    uma ação potencialmente destrutiva ou de execução arbitrária.

    A função é deliberadamente conservadora, mas não bloqueia perguntas
    ou explicações sobre essas ações.
    """
    texto_norm = normalizar_texto(
        str(texto or "")
    )

    if not texto_norm:
        return False

    if _parece_pergunta_ou_explicacao(
        texto_norm
    ):
        return False

    if _parece_negacao(
        texto_norm
    ):
        return False

    return any(
        re.search(
            padrao,
            texto_norm,
            flags=re.IGNORECASE,
        )
        for padrao in _PADROES_ACAO_PERIGOSA
    )


def resposta_acao_perigosa():
    return (
        "Essa ação é perigosa e precisa de confirmação manual. "
        "Não vou executar automaticamente."
    )