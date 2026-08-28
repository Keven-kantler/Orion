import re
import unicodedata


def log(mensagem):
    print(mensagem)


def normalizar_texto(texto):
    """
    Normaliza texto para comparação interna.

    Mantém o comportamento anterior para strings normais:
    - minúsculas
    - sem acentos
    - espaços duplicados removidos

    Agora também aceita None e valores não-string sem derrubar o Orion.
    """
    if texto is None:
        return ""

    texto = str(texto).lower().strip()

    if not texto:
        return ""

    texto = unicodedata.normalize(
        "NFD",
        texto,
    )

    texto = "".join(
        char
        for char in texto
        if unicodedata.category(char) != "Mn"
    )

    return re.sub(
        r"\s+",
        " ",
        texto,
    )


def limpar_resposta_ia(texto):
    """
    Limpa caracteres/formatação indesejados antes de a resposta ser falada.

    Preserva o comportamento atual do Orion de remover caracteres CJK e
    marcações Markdown simples.
    """
    if texto is None:
        return ""

    texto = str(texto)

    texto = re.sub(
        r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
        r"\u3040-\u30ff\u3130-\u318f\uac00-\ud7af]",
        "",
        texto,
    )

    texto = re.sub(
        r"[*_`#>\[\]]+",
        "",
        texto,
    )

    texto = re.sub(
        r"\s+",
        " ",
        texto,
    )

    return texto.strip()


def limitar_resposta(
    texto,
    max_frases=3,
    max_chars=500,
):
    """
    Limita respostas longas para o formato falado do Orion.

    Continua priorizando quantidade de frases e, depois, limite de caracteres.
    """
    if texto is None:
        return ""

    texto = str(texto).strip()

    if not texto:
        return ""

    try:
        max_frases = int(max_frases)
    except (TypeError, ValueError):
        max_frases = 3

    try:
        max_chars = int(max_chars)
    except (TypeError, ValueError):
        max_chars = 500

    if max_frases <= 0 or max_chars <= 0:
        return ""

    frases = re.findall(
        r"[^.!?]+[.!?]*",
        texto,
    )

    frases = [
        frase.strip()
        for frase in frases
        if frase.strip()
    ]

    if frases:
        texto = " ".join(
            frases[:max_frases]
        ).strip()

    if len(texto) > max_chars:
        if max_chars <= 3:
            return texto[:max_chars]

        texto = (
            texto[: max_chars - 3].rstrip()
            + "..."
        )

    return texto


def _contem_frase_inteira(texto, candidato):
    """
    Verifica palavra/frase inteira, evitando falso positivo por substring.

    Exemplos:
        "metal" em "toca metal"      -> True
        "metal" em "metallica"       -> False
        "rock" em "rock alternativo" -> True
    """
    texto_norm = normalizar_texto(texto)
    candidato_norm = normalizar_texto(candidato)

    if not texto_norm or not candidato_norm:
        return False

    padrao = (
        r"(?<!\w)"
        + re.escape(candidato_norm)
        + r"(?!\w)"
    )

    return bool(
        re.search(
            padrao,
            texto_norm,
        )
    )


def contem_aproximado(
    texto,
    candidatos,
    limite=82,
):
    """
    Detecta termos aproximados sem confundir substring com palavra inteira.

    A interface permanece idêntica à versão antiga.
    """
    texto_norm = normalizar_texto(texto)

    if not texto_norm:
        return False

    if isinstance(candidatos, str):
        candidatos = (candidatos,)

    candidatos_norm = [
        normalizar_texto(candidato)
        for candidato in candidatos
        if normalizar_texto(candidato)
    ]

    if not candidatos_norm:
        return False

    # Primeiro tenta correspondência exata por palavra/frase.
    for candidato in candidatos_norm:
        if _contem_frase_inteira(
            texto_norm,
            candidato,
        ):
            return True

    try:
        from rapidfuzz import fuzz
    except ImportError:
        return False

    try:
        limite = float(limite)
    except (TypeError, ValueError):
        limite = 82.0

    palavras = texto_norm.split()

    # Janelas de 1 a 4 palavras preservam o comportamento original,
    # mas evitam comparar candidatos contra substrings arbitrárias.
    janelas = set()

    for tamanho in range(
        1,
        min(4, len(palavras)) + 1,
    ):
        for indice in range(
            0,
            len(palavras) - tamanho + 1,
        ):
            janelas.add(
                " ".join(
                    palavras[
                        indice:
                        indice + tamanho
                    ]
                )
            )

    for candidato in candidatos_norm:
        for janela in janelas:
            # Evita que termos curtos sejam aceitos por aproximação dentro
            # de palavras maiores, como "metal" vs "metallica".
            if (
                len(candidato) <= 5
                and len(janela) > len(candidato) + 2
            ):
                continue

            if (
                fuzz.ratio(
                    janela,
                    candidato,
                )
                >= limite
            ):
                return True

    return False


def remover_prefixos(
    texto,
    prefixos,
):
    """
    Remove o primeiro prefixo correspondente usando a forma normalizada.

    Mantém o contrato antigo: o retorno também é normalizado.
    Isso é importante para não quebrar o intent_router.py.
    """
    texto_norm = normalizar_texto(
        texto
    )

    if not texto_norm:
        return ""

    if isinstance(prefixos, str):
        prefixos = (prefixos,)

    for prefixo in prefixos:
        prefixo_norm = normalizar_texto(
            prefixo
        )

        if (
            prefixo_norm
            and texto_norm.startswith(
                prefixo_norm
            )
        ):
            return texto_norm[
                len(prefixo_norm):
            ].strip()

    return texto_norm