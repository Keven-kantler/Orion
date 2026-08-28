from urllib.parse import urlparse

from utils import normalizar_texto

try:
    from ddgs import DDGS
except ImportError:
    DDGS = None


def _parece_declaracao_pessoal(pergunta_norm):
    """
    Detecta frases declarativas do usuário que não precisam de internet.

    Exemplos:
    - meu jogo favorito é Cyberpunk 2077
    - minha linguagem preferida é Python
    - eu gosto de God of War
    - estou desenvolvendo o Orion
    """
    prefixos = (
        "meu ",
        "minha ",
        "meus ",
        "minhas ",
        "eu gosto ",
        "eu adoro ",
        "eu amo ",
        "eu prefiro ",
        "eu trabalho ",
        "eu estudo ",
        "eu estou fazendo ",
        "eu estou criando ",
        "eu estou desenvolvendo ",
        "estou fazendo ",
        "estou criando ",
        "estou desenvolvendo ",
    )

    return pergunta_norm.startswith(prefixos)


def _parece_consulta_memoria_pessoal(pergunta_norm):
    """
    Evita mandar consultas sobre a memória pessoal do usuário para a web.
    """
    marcadores_pessoais = (
        " meu ",
        " minha ",
        " meus ",
        " minhas ",
        " sobre mim ",
        " eu disse ",
        " eu falei ",
        " eu te disse ",
        " eu te falei ",
        " que eu gosto ",
        " que eu prefiro ",
    )

    texto = f" {pergunta_norm} "

    if any(
        marcador in texto
        for marcador in marcadores_pessoais
    ):
        return True

    prefixos_memoria = (
        "o que voce lembra",
        "o que voce sabe sobre mim",
        "o que eu te falei",
        "o que eu te disse",
        "voce lembra meu",
        "voce lembra minha",
        "voce lembra meus",
        "voce lembra minhas",
        "voce lembra qual e meu",
        "voce lembra qual e o meu",
        "voce lembra qual e minha",
        "voce lembra qual e a minha",
    )

    return pergunta_norm.startswith(prefixos_memoria)


def _pedido_explicito_web(pergunta_norm):
    """
    Quando o usuário explicitamente pede pesquisa, a intenção é inequívoca.
    """
    gatilhos = (
        "pesquise na internet",
        "pesquisa na internet",
        "procure na internet",
        "procura na internet",
        "busque na internet",
        "busca na internet",
        "pesquise na web",
        "pesquisa na web",
        "procure na web",
        "procura na web",
        "busque na web",
        "busca na web",
        "pesquise online",
        "pesquisa online",
        "procure online",
        "procura online",
        "veja na internet",
        "olhe na internet",
        "consulte a internet",
    )

    return any(
        gatilho in pergunta_norm
        for gatilho in gatilhos
    )


def _tem_gatilho_atualidade(pergunta_norm):
    """
    Detecta pedidos que dependem claramente de informação recente.

    Importante: não considera palavras interrogativas genéricas como
    "quem", "o que", "quanto" ou "me explica" como motivo para usar web.
    """
    gatilhos = (
        "hoje",
        "agora",
        "neste momento",
        "atual",
        "atuais",
        "atualmente",
        "mais recente",
        "mais recentes",
        "ultima noticia",
        "ultimas noticias",
        "noticia recente",
        "noticias recentes",
        "novidade",
        "novidades",
        "acabou de",
        "essa semana",
        "esta semana",
        "este mes",
        "esse mes",
        "neste mes",
        "ano atual",
        "esse ano",
        "este ano",
    )

    return any(
        gatilho in pergunta_norm
        for gatilho in gatilhos
    )


def _tema_intrinsecamente_volatil(pergunta_norm):
    """
    Alguns assuntos mudam rápido mesmo quando o usuário não diz "hoje".

    Nesses casos é melhor pesquisar do que deixar o modelo local responder
    com dado potencialmente desatualizado.
    """
    termos = (
        # Mercado / preços / câmbio
        "cotacao",
        "dolar",
        "euro",
        "bitcoin",
        "criptomoeda",
        "preco da acao",
        "preco das acoes",
        "bolsa de valores",
        "ibovespa",
        "taxa selic",

        # Clima
        "temperatura",
        "previsao do tempo",
        "clima em",
        "vai chover",
        "vai fazer frio",
        "vai fazer calor",

        # Notícias / política e cargos atuais
        "presidente do brasil",
        "presidente dos estados unidos",
        "presidente dos eua",
        "primeiro ministro",
        "primeira ministra",
        "ceo da",
        "ceo do",
        "diretor executivo",
        "governador de",
        "prefeito de",

        # Esportes / resultados recentes
        "placar",
        "resultado do jogo",
        "resultado da partida",
        "classificacao do campeonato",
        "tabela do campeonato",

        # Produtos/software que mudam
        "versao mais recente",
        "ultima versao",
        "versao atual",
        "preco do",
        "preco da",
        "quanto custa",
        "esta custando",

        # Agenda / disponibilidade / lançamentos
        "data de lancamento",
        "quando vai lancar",
        "quando estreia",
        "quando vai estrear",
        "agenda de",
    )

    return any(
        termo in pergunta_norm
        for termo in termos
    )


def precisa_pesquisar(pergunta):
    """
    Decide se a pergunta deve consultar a internet.

    Regra central:
    - conhecimento geral -> modelo local;
    - memória pessoal -> local;
    - informação explicitamente atual/volátil -> web;
    - pedido explícito de pesquisa -> web.

    Isso evita o comportamento antigo em que qualquer pergunta iniciada por
    "o que é", "quem é", "quanto" ou "me explica" acionava a internet.
    """
    pergunta_norm = normalizar_texto(pergunta)

    if not pergunta_norm:
        return False

    if _parece_declaracao_pessoal(pergunta_norm):
        print(
            "Busca web ignorada: "
            "declaração pessoal detectada."
        )
        return False

    if _parece_consulta_memoria_pessoal(pergunta_norm):
        print(
            "Busca web ignorada: "
            "consulta de memoria pessoal detectada."
        )
        return False

    if _pedido_explicito_web(pergunta_norm):
        return True

    if _tem_gatilho_atualidade(pergunta_norm):
        return True

    if _tema_intrinsecamente_volatil(pergunta_norm):
        return True

    return False


def _resultado_valido(resultado):
    return (
        isinstance(resultado, dict)
        and any(
            str(resultado.get(chave, "") or "").strip()
            for chave in ("title", "body", "href")
        )
    )


def _normalizar_link(link):
    link = str(link or "").strip()

    if not link:
        return ""

    try:
        parsed = urlparse(link)

        if parsed.scheme not in {"http", "https"}:
            return ""

        return link
    except Exception:
        return ""


def pesquisar_web(pergunta):
    """
    Executa uma busca textual simples no DuckDuckGo via DDGS.

    Retorna no máximo três resultados no contrato já usado pelo brain.py:
    {
        "titulo": str,
        "resumo": str,
        "link": str,
    }
    """
    pergunta = str(pergunta or "").strip()

    if not pergunta:
        return []

    print("Pesquisando na web...")

    if DDGS is None:
        print(
            "Busca web indisponível: instale ddgs."
        )
        return []

    resultados = []
    links_vistos = set()

    try:
        with DDGS() as ddgs:
            resposta = ddgs.text(
                pergunta,
                max_results=5,
                region="br-pt",
            )

            for resultado in resposta:
                if not _resultado_valido(resultado):
                    continue

                titulo = str(
                    resultado.get("title", "") or ""
                ).strip()

                resumo = str(
                    resultado.get("body", "") or ""
                ).strip()

                link = _normalizar_link(
                    resultado.get("href", "")
                )

                # Evita repetir a mesma página.
                if link and link in links_vistos:
                    continue

                if link:
                    links_vistos.add(link)

                item = {
                    "titulo": titulo,
                    "resumo": resumo,
                    "link": link,
                }

                resultados.append(item)

                if link:
                    print(
                        f"Link encontrado: {link}"
                    )

                if len(resultados) >= 3:
                    break

    except Exception as erro:
        print(
            "Erro na busca web:",
            erro,
        )
        return []

    return resultados


def formatar_resultados(resultados):
    """
    Formata resultados para o prompt do brain.py.

    É tolerante a itens incompletos para que uma resposta malformada do
    provedor de busca não derrube o Orion.
    """
    if not resultados:
        return ""

    linhas = []

    for indice, resultado in enumerate(
        resultados,
        start=1,
    ):
        if not isinstance(resultado, dict):
            continue

        titulo = str(
            resultado.get("titulo", "") or ""
        ).strip()

        resumo = str(
            resultado.get("resumo", "") or ""
        ).strip()

        link = str(
            resultado.get("link", "") or ""
        ).strip()

        if not any((titulo, resumo, link)):
            continue

        linhas.append(
            f"Resultado {indice}: "
            f"Título: {titulo} | "
            f"Resumo: {resumo} | "
            f"Link: {link}"
        )

    return "\n".join(linhas)