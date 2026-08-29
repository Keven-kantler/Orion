import json
import re
import time
import unicodedata
from collections import deque

try:
    import ollama
except ImportError:  # Permite testar os caminhos determinísticos sem Ollama instalado.
    ollama = None

from config import MODELO_ROUTER


# =========================================================
# INTENÇÕES AUTORIZADAS
# =========================================================

INTENTS_PERMITIDAS = {
    "tocar_musica",
    "proxima_musica",
    "musica_anterior",
    "pausar_musica",
    "continuar_musica",

    "abrir_spotify",
    "abrir_aplicativo",
    "abrir_site",

    "pesquisar_youtube",
    "pesquisar_google",

    "aumentar_volume",
    "diminuir_volume",
    "mutar_volume",
    "desmutar_volume",

    "falar_hora_atual",

    "criar_nota",
    "ler_notas",
    "salvar_memoria",
    "consultar_memoria",
    "atualizar_memoria",
    "apagar_memoria",

    "conversar",
    "nao_entendi",
}


# =========================================================
# PROMPT DO ROUTER
# =========================================================

SYSTEM_PROMPT_ROUTER = """
Você é o roteador de intenções do Orion,
um assistente pessoal de computador.

Sua função NÃO é responder ao usuário.

Sua única função é:

1. Entender o que o usuário deseja.
2. Escolher UMA intenção autorizada.
3. Extrair apenas os parâmetros realmente presentes
   ou claramente identificáveis na mensagem.
4. Retornar somente JSON válido.

Não use Markdown.
Não explique sua decisão.
Não converse com o usuário.
Não invente informações.


============================================================
INTENÇÕES DISPONÍVEIS
============================================================

tocar_musica
proxima_musica
musica_anterior
pausar_musica
continuar_musica

abrir_spotify
abrir_aplicativo
abrir_site

pesquisar_youtube
pesquisar_google

aumentar_volume
diminuir_volume
mutar_volume
desmutar_volume

falar_hora_atual

criar_nota
ler_notas
salvar_memoria
consultar_memoria
atualizar_memoria
apagar_memoria

conversar
nao_entendi


============================================================
FORMATO OBRIGATÓRIO
============================================================

{
  "intent": "nome_da_intencao",
  "parameters": {}
}


============================================================
CONVERSA
============================================================

Use "conversar" quando a mensagem for:

- uma pergunta;
- um pedido de explicação;
- um pedido de opinião;
- uma continuação de conversa;
- uma curiosidade;
- uma pergunta sobre algo dito anteriormente;
- qualquer conversa que não seja uma ferramenta disponível.

Uma pergunta NÃO vira "nao_entendi" apenas porque depende
do contexto anterior.

Exemplos:

"por que o céu é azul?"
→ conversar

"porque o céu é azul?"
→ conversar

"o que você achou?"
→ conversar

"e por quê?"
→ conversar

"e depois?"
→ conversar

"como assim?"
→ conversar

"como funciona uma CPU?"
→ conversar

"me explica computação quântica"
→ conversar

"quem é Tony Stark?"
→ conversar

"qual a distância da Terra até a Lua?"
→ conversar

"você gosta de rock?"
→ conversar

Declarações do usuário sobre si mesmo, preferências, rotina,
projetos, opiniões ou fatos pessoais também são conversa,
mesmo quando contêm nomes que poderiam existir no Spotify.

Exemplos:

"meu jogo favorito é Cyberpunk 2077"
→ conversar

"meu jogo favorito é God of War"
→ conversar

"Roblox é um dos meus jogos favoritos"
→ conversar

"eu gosto muito de Cyberpunk 2077"
→ conversar

"meu artista favorito é AC/DC"
→ conversar

IMPORTANTE:
Não use "tocar_musica" apenas porque a frase contém nome de
música, artista, jogo, filme ou outra entidade encontrada no Spotify.
Use "tocar_musica" somente quando houver intenção de ouvir/tocar música.

"isso é perigoso?"
→ conversar

"e no meu caso?"
→ conversar


============================================================
NÃO ENTENDI
============================================================

Use "nao_entendi" SOMENTE quando não for possível
determinar com segurança o que o usuário quis dizer.

Isso acontece principalmente quando:

- a transcrição parece corrompida;
- há palavras sem sentido;
- uma ação precisa de um parâmetro essencial que não existe;
- existe ambiguidade real sobre qual ação executar.

Exemplos:

"manda a certeza"
→ nao_entendi

"toca icgca"
→ nao_entendi

"abre aquilo"
→ nao_entendi

"coloca o negócio"
→ nao_entendi

"faz aquele negócio"
→ nao_entendi


============================================================
REGRA CRÍTICA: NÃO INVENTE PARÂMETROS
============================================================

Nunca invente:

- artista;
- música;
- aplicativo;
- site;
- consulta de pesquisa;
- qualquer outro parâmetro.

Os parâmetros devem existir na mensagem do usuário.

Você pode apenas NORMALIZAR algo quando a correspondência
for evidente.

Exemplos permitidos:

"ac dc"
→ "AC/DC"

"acdc"
→ "AC/DC"

"guns n roses"
→ "Guns N' Roses"

"youtube"
→ "youtube"

Exemplos proibidos:

"icgca"
→ NÃO transformar em AC/DC

"manda a certeza"
→ NÃO transformar em The Beatles

"toca aquela"
→ NÃO inventar nome de música


============================================================
MÚSICA
============================================================

Use "tocar_musica" somente quando o usuário demonstrar
intenção de reproduzir/ouvir música, por exemplo com verbos ou
expressões como "toca", "coloca", "manda", "quero ouvir",
"bota para tocar" ou equivalentes.

Não classifique uma simples declaração como música.

"meu jogo favorito é Cyberpunk 2077"
→ conversar

"eu gosto de God of War"
→ conversar

"meu artista favorito é AC/DC"
→ conversar

"toca AC/DC"
→ tocar_musica

"quero ouvir Back in Black"
→ tocar_musica

Para tocar uma música específica:

{
  "intent": "tocar_musica",
  "parameters": {
    "tipo": "musica",
    "consulta": "nome da música"
  }
}

Exemplo:

"quero back in black"

{
  "intent": "tocar_musica",
  "parameters": {
    "tipo": "musica",
    "consulta": "Back in Black"
  }
}


Para tocar um artista:

{
  "intent": "tocar_musica",
  "parameters": {
    "tipo": "artista",
    "consulta": "nome do artista"
  }
}

Exemplo:

"manda um ac dc aí"

{
  "intent": "tocar_musica",
  "parameters": {
    "tipo": "artista",
    "consulta": "AC/DC"
  }
}


Para gênero musical:

{
  "intent": "tocar_musica",
  "parameters": {
    "tipo": "genero",
    "consulta": "rock"
  }
}


============================================================
CONTROLE DE MÚSICA
============================================================

"pula essa"
→ proxima_musica

"volta a música"
→ musica_anterior

"pausa"
→ pausar_musica

"continua"
→ continuar_musica


============================================================
APLICATIVOS
============================================================

"abre o discord"

{
  "intent": "abrir_aplicativo",
  "parameters": {
    "aplicativo": "discord"
  }
}


============================================================
PESQUISAS
============================================================

"procura vídeos sobre buracos negros no youtube"

{
  "intent": "pesquisar_youtube",
  "parameters": {
    "consulta": "buracos negros"
  }
}

"pesquisa buracos negros no google"

{
  "intent": "pesquisar_google",
  "parameters": {
    "consulta": "buracos negros"
  }
}


============================================================
VOLUME
============================================================

Se o usuário disser que o som, áudio ou volume está
muito ALTO, escolha "diminuir_volume".

Exemplos:

"esse som está muito alto"
"o áudio está alto"
"está alto demais"
"abaixa um pouco"
"reduz o volume"

Resposta:

{
  "intent": "diminuir_volume",
  "parameters": {
    "acao": "diminuir"
  }
}


Se o usuário disser que o som, áudio ou volume está
muito BAIXO, escolha "aumentar_volume".

Exemplos:

"o áudio está muito baixo"
"esse som está baixo"
"está muito baixo"
"aumenta um pouco"
"sobe o volume"
"quase não estou ouvindo"

Resposta:

{
  "intent": "aumentar_volume",
  "parameters": {
    "acao": "aumentar"
  }
}


Para silenciar:

"fica mudo"
"muta o som"
"silencia"

Resposta:

{
  "intent": "mutar_volume",
  "parameters": {
    "acao": "mutar"
  }
}


Para retirar o mudo:

"tira do mudo"
"desmuta"
"volta o som"

Resposta:

{
  "intent": "desmutar_volume",
  "parameters": {
    "acao": "desmutar"
  }
}
============================================================
MEMÓRIA
============================================================

Use "salvar_memoria" quando o usuário pedir explicitamente
para lembrar, guardar, registrar ou memorizar uma informação
para uso futuro.

Exemplos:

"lembra que meu projeto principal usa Python"

{
  "intent": "salvar_memoria",
  "parameters": {
    "conteudo": "meu projeto principal usa Python",
    "categoria": "notas"
  }
}

"guarda que quero adicionar reconhecimento facial ao Orion"

{
  "intent": "salvar_memoria",
  "parameters": {
    "conteudo": "quero adicionar reconhecimento facial ao Orion",
    "categoria": "notas"
  }
}

Nunca invente o conteúdo da memória.


============================================================
CONSULTAR MEMÓRIA
============================================================

Use "consultar_memoria" quando o usuário perguntar
explicitamente sobre algo que pediu anteriormente para
o Orion lembrar, guardar ou memorizar.

Exemplos:

"o que você lembra sobre reconhecimento facial?"

{
  "intent": "consultar_memoria",
  "parameters": {
    "consulta": "reconhecimento facial"
  }
}

"o que eu te falei sobre reconhecimento facial?"

{
  "intent": "consultar_memoria",
  "parameters": {
    "consulta": "reconhecimento facial"
  }
}

"você lembra do reconhecimento facial?"

{
  "intent": "consultar_memoria",
  "parameters": {
    "consulta": "reconhecimento facial"
  }
}

Não confunda consulta de memória com pergunta comum.

"como funciona reconhecimento facial?"
→ conversar

"o que você lembra sobre reconhecimento facial?"
→ consultar_memoria


============================================================
ATUALIZAR MEMÓRIA
============================================================

Use "atualizar_memoria" quando o usuário pedir explicitamente
para corrigir, alterar ou atualizar uma informação já lembrada.

Exemplos:

"corrija o nome da minha namorada para Evelyn"

{
  "intent": "atualizar_memoria",
  "parameters": {
    "consulta": "nome da minha namorada",
    "novo_conteudo": "o nome da minha namorada é Evelyn"
  }
}

"corrija o nome da minha namorada. o nome dela é Evelyn"

{
  "intent": "atualizar_memoria",
  "parameters": {
    "consulta": "nome da minha namorada",
    "novo_conteudo": "o nome dela é Evelyn"
  }
}

Se o usuário disser apenas "corrija" sem indicar o que deve
ser corrigido e sem contexto suficiente, use "nao_entendi".

Se a fala atual trouxer apenas a mudança, como "corrija para X",
"mude para X", "altere para X" ou "atualize para X", mas o contexto
recente deixar claro qual informação de memória está em foco, use
essa informação anterior como "consulta" e X como o novo valor.

Exemplo de continuação:

Contexto recente:
"qual é o meu editor favorito?"

Fala atual:
"corrija para VS Code"

Resultado:
{
  "intent": "atualizar_memoria",
  "parameters": {
    "consulta": "meu editor favorito",
    "novo_conteudo": "meu editor favorito é VS Code"
  }
}

Essa regra vale de forma geral para qualquer informação em foco,
não apenas para este exemplo.


============================================================
APAGAR MEMÓRIA
============================================================

Use "apagar_memoria" quando o usuário pedir explicitamente
para esquecer, apagar ou remover uma informação da memória.

Exemplos:

"esquece o nome da minha namorada"

{
  "intent": "apagar_memoria",
  "parameters": {
    "consulta": "nome da minha namorada"
  }
}

"apaga da memória meu jogo favorito"

{
  "intent": "apagar_memoria",
  "parameters": {
    "consulta": "meu jogo favorito"
  }
}


============================================================
REGRA FINAL
============================================================

Se for uma frase perfeitamente compreensível como pergunta
ou conversa, use "conversar".

Use "nao_entendi" apenas quando realmente não for possível
entender a mensagem ou executar uma ação com segurança.
"""


# =========================================================
# NORMALIZAÇÃO / VALIDAÇÃO
# =========================================================

def normalizar_para_validacao(texto):
    texto = str(texto or "").lower()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    return re.sub(
        r"[^a-z0-9]",
        "",
        texto,
    )


def normalizar_com_espacos(texto):
    texto = str(texto or "").lower()

    texto = unicodedata.normalize(
        "NFKD",
        texto,
    )

    texto = "".join(
        caractere
        for caractere in texto
        if not unicodedata.combining(caractere)
    )

    texto = re.sub(
        r"[^a-z0-9\s]",
        " ",
        texto,
    )

    return re.sub(r"\s+", " ", texto).strip()


def limpar_consulta_memoria(consulta):
    consulta = str(consulta or "").strip()
    consulta = consulta.strip(" .,!?:;")

    prefixos = (
        "qual e ",
        "qual eh ",
        "qual ",
        "o que voce lembra sobre ",
        "o que voce lembra de ",
        "o que eu te falei sobre ",
        "o que eu te disse sobre ",
        "o que voce sabe sobre ",
        "voce lembra qual e ",
        "voce lembra qual ",
        "voce lembra ",
    )

    consulta_norm = normalizar_com_espacos(consulta)

    for prefixo in prefixos:
        if consulta_norm.startswith(prefixo):
            consulta_norm = consulta_norm[len(prefixo):].strip()
            break

    return consulta_norm or consulta


def texto_tem_marcador_pessoal(texto_norm):
    marcadores = (
        " meu ",
        " minha ",
        " meus ",
        " minhas ",
        " mim",
        " sobre mim",
        " eu disse",
        " eu falei",
        " eu te disse",
        " eu te falei",
        " que eu gosto",
        " que eu prefiro",
        " minha namorada",
        " meu namorado",
        " meu projeto",
        " meus projetos",
    )

    texto_com_espacos = f" {texto_norm} "

    return any(
        marcador in texto_com_espacos
        for marcador in marcadores
    )


def consulta_esta_no_texto(texto_original, consulta):
    """
    Impede a LLM de inventar consultas.

    Exemplo válido:
        texto: "manda um ac dc aí"
        consulta: "AC/DC"

        normalizado:
        mandaumacdcai
        acdc

        -> válido

    Exemplo inválido:
        texto: "toca icgca"
        consulta: "AC/DC"

        -> bloqueado
    """

    if not consulta:
        return True

    texto_norm = normalizar_para_validacao(
        texto_original
    )

    consulta_norm = normalizar_para_validacao(
        consulta
    )

    if not consulta_norm:
        return True

    return consulta_norm in texto_norm


def parametro_tem_palavra_do_texto(texto_original, parametro):
    texto_norm = normalizar_com_espacos(texto_original)
    parametro_norm = normalizar_com_espacos(parametro)

    if not parametro_norm:
        return True

    ignoradas = {
        "o",
        "a",
        "os",
        "as",
        "um",
        "uma",
        "de",
        "do",
        "da",
        "dos",
        "das",
        "meu",
        "minha",
        "meus",
        "minhas",
        "para",
        "que",
        "e",
        "eh",
        "sao",
    }

    palavras_texto = set(texto_norm.split())
    palavras_parametro = {
        palavra
        for palavra in parametro_norm.split()
        if len(palavra) >= 3 and palavra not in ignoradas
    }

    if not palavras_parametro:
        return True

    return bool(palavras_texto.intersection(palavras_parametro))


# =========================================================
# DETECTOR RÁPIDO DE CONVERSA
# =========================================================

def fala_depende_de_contexto(texto):
    """Indica quando a fala atual realmente precisa do turno anterior."""

    texto_norm = normalizar_com_espacos(texto)

    if not texto_norm:
        return False

    padroes = (
        r"^(?:e|mas|entao|agora)\b",
        r"^(?:ele|ela|eles|elas|isso|isto|esse|essa|esses|essas|"
        r"aquele|aquela|aqueles|aquelas|dele|dela|deles|delas)\b",
        r"^(?:quando|onde|como|por que|porque|quem)\??$",
        r"^(?:e\s+)?(?:quando|onde|como|por que|porque|quem)\b",
        r"^(?:corrija|corrige|mude|muda|altere|altera|"
        r"atualize|atualiza)(?:\s+isso)?\s+para\s+.+$",
    )

    return any(re.search(padrao, texto_norm) for padrao in padroes)


def parece_conversa(texto):
    """
    Detecta perguntas/conversas óbvias antes de chamar o modelo pequeno.

    Importante: uma frase terminar com "?" não basta para classificá-la
    como conversa. Comandos naturais também podem ser formulados como
    pergunta (ex.: "pode abrir o Spotify?"). Esses casos seguem para o
    router semântico em vez de serem interceptados aqui.
    """

    texto_norm = normalizar_com_espacos(texto)

    if not texto_norm:
        return False

    # Verbos/expressões que indicam uma ação disponível no Orion.
    # Se aparecerem no começo da fala, deixamos o router decidir a ação.
    prefixos_acao = (
        "abre ", "abra ", "abrir ",
        "fecha ", "feche ", "fecho ", "fechar ",
        "encerra ", "encerre ", "encerro ", "encerrar ",
        "toca ", "toque ", "tocar ",
        "coloca ", "coloque ", "bota ", "bote ", "manda ",
        "pausa ", "pause ", "continua ", "continue ",
        "proxima ", "proximo ", "anterior ",
        "pesquisa ", "pesquise ", "procura ", "procure ",
        "aumenta ", "aumente ", "abaixa ", "abaixe ",
        "diminui ", "diminua ", "muta ", "desmuta ",
        "cria uma nota", "crie uma nota", "anota ", "anote ",
        "que horas ",
    )

    prefixos_cortesia_acao = (
        "pode ",
        "poderia ",
        "consegue ",
        "conseguiria ",
        "por favor ",
    )

    if texto_norm.startswith(prefixos_acao):
        return False

    if texto_norm.startswith(prefixos_cortesia_acao):
        restante = texto_norm
        for prefixo in prefixos_cortesia_acao:
            if restante.startswith(prefixo):
                restante = restante[len(prefixo):].strip()
                break
        if restante.startswith(prefixos_acao):
            return False

    prefixos_conversa = (
        "por que ",
        "porque ",
        "por que",
        "como ",
        "quem ",
        "quando ",
        "onde ",
        "qual ",
        "quais ",
        "quanto ",
        "quantos ",
        "quantas ",
        "o que ",
        "me explica",
        "me explique",
        "me conta",
        "me conte",
        "voce acha",
        "voce sabe",
        "voce gosta",
        "o que voce acha",
        "o que voce achou",
        "e por que",
        "e porque",
        "e depois",
        "e como",
        "como assim",
        "e no meu caso",
    )

    if texto_norm.startswith(prefixos_conversa):
        return True

    falas_sociais = {
        "obrigado", "obrigada", "valeu", "brigado", "brigada",
        "bom dia", "boa tarde", "boa noite", "ate mais", "falou",
    }

    if texto_norm in falas_sociais:
        return True

    # Continuação curta pode vir sem interrogação porque o Whisper nem
    # sempre preserva a pontuação da fala.
    if re.match(
        r"^(?:ele|ela|eles|elas|isso|isto|esse|essa|esses|essas|"
        r"aquele|aquela|aqueles|aquelas|dele|dela|deles|delas)\b",
        texto_norm,
    ):
        return True

    if re.match(
        r"^(?:mas|e)\s+(?:ele|ela|eles|elas|isso|isto|esse|essa)\b",
        texto_norm,
    ):
        return True

    # Perguntas sem um verbo de ferramenta explícito continuam sendo
    # conversa. A checagem de ação acima impede o falso positivo mais
    # perigoso do comportamento antigo.
    return str(texto or "").strip().endswith("?")


def texto_autoriza_operacao_memoria(texto, intent):
    """Exige evidência explícita antes de aceitar intents que alteram memória."""
    texto_norm = normalizar_com_espacos(texto)

    if intent == "apagar_memoria":
        gatilhos = (
            "esqueca", "esquece", "apague", "apaga", "delete", "deleta",
            "remova", "remove", "tire da memoria", "apague da memoria",
        )
        return any(gatilho in texto_norm for gatilho in gatilhos)

    if intent == "atualizar_memoria":
        gatilhos = (
            "corrija", "corrige", "mude", "muda", "altere", "altera",
            "atualize", "atualiza", "troque", "troca",
        )
        return any(gatilho in texto_norm for gatilho in gatilhos)

    if intent == "salvar_memoria":
        gatilhos = (
            "lembre", "lembra", "memorize", "memoriza", "guarde", "guarda",
            "salve na memoria", "salva na memoria",
        )
        return any(gatilho in texto_norm for gatilho in gatilhos)

    return True


# =========================================================
# DETECTOR RÁPIDO DE DECLARAÇÃO / PREFERÊNCIA
# =========================================================

def detectar_declaracao_usuario_rapida(texto):
    """
    Detecta declarações claras do usuário antes do router semântico.

    Isso evita que nomes de jogos, artistas, filmes ou outras entidades
    sejam confundidos com pedidos para tocar algo no Spotify.

    Exemplos:
        "meu jogo favorito é Cyberpunk 2077" -> conversar
        "eu gosto muito de God of War" -> conversar
        "meu editor preferido é VS Code" -> conversar

    Comandos explícitos continuam indo para o router:
        "toca Cyberpunk 2077" -> não entra aqui
        "quero ouvir AC/DC" -> não entra aqui
    """

    texto_norm = str(texto or "").strip().lower()

    if not texto_norm:
        return None

    # Se existe intenção explícita de executar uma ação, não intercepta.
    comandos_acao = (
        "toca ",
        "toque ",
        "coloca ",
        "coloque ",
        "bota ",
        "bote ",
        "manda ",
        "quero ouvir ",
        "quero escutar ",
        "abre ",
        "abra ",
        "pesquisa ",
        "pesquise ",
        "procura ",
        "procure ",
    )

    if texto_norm.startswith(comandos_acao):
        return None

    padroes_declaracao = (
        r"^(?:o\s+)?meu\s+.+\s+(?:favorito|favorita|preferido|preferida)\s+(?:é|e)\s+.+",
        r"^(?:os\s+)?meus\s+.+\s+(?:favoritos|preferidos)\s+(?:são|sao)\s+.+",
        r"^(?:a\s+)?minha\s+.+\s+(?:favorita|preferida)\s+(?:é|e)\s+.+",
        r"^(?:as\s+)?minhas\s+.+\s+(?:favoritas|preferidas)\s+(?:são|sao)\s+.+",
        r"^eu\s+(?:gosto|adoro|amo|prefiro)\s+.+",
        r"^eu\s+não\s+gosto\s+.+",
        r"^eu\s+nao\s+gosto\s+.+",
        r"^estou\s+(?:fazendo|criando|desenvolvendo|trabalhando)\s+.+",
        r"^meu\s+projeto\s+.+",
        r"^minha\s+ideia\s+.+",
    )

    if any(
        re.search(padrao, texto_norm)
        for padrao in padroes_declaracao
    ):
        return {
            "intent": "conversar",
            "parameters": {},
        }

    return None


# =========================================================
# DETECTOR RÁPIDO DE VOLUME
# =========================================================

def detectar_volume_rapido(texto):
    """
    Resolve linguagem natural simples de volume sem chamar
    o modelo 1.5B.

    Exemplos:
        "o áudio está muito baixo" -> aumentar
        "esse som está muito alto" -> diminuir

    Retorna None quando não houver evidência suficiente.
    """

    texto_norm = str(texto or "").strip().lower()

    if not texto_norm:
        return None

    # Só entra nesta regra quando existe contexto claro de áudio.
    fala_de_volume = any(
        termo in texto_norm
        for termo in (
            "volume",
            "som",
            "áudio",
            "audio",
        )
    )

    if not fala_de_volume:
        return None

    aumentar = (
        "muito baixo",
        "está baixo",
        "esta baixo",
        "som baixo",
        "áudio baixo",
        "audio baixo",
        "volume baixo",
        "baixo demais",
        "aumenta",
        "aumentar",
        "sobe o volume",
        "sube o volume",
        "mais volume",
        "quase não estou ouvindo",
        "quase nao estou ouvindo",
        "quase não ouço",
        "quase nao ouco",
    )

    diminuir = (
        "muito alto",
        "está alto",
        "esta alto",
        "som alto",
        "áudio alto",
        "audio alto",
        "volume alto",
        "alto demais",
        "abaixa",
        "abaixe",
        "diminuir",
        "diminui",
        "reduz",
        "reduzir",
        "menos volume",
    )

    mutar = (
        "fica mudo",
        "ficar mudo",
        "muta",
        "mutar",
        "silencia",
        "silenciar",
        "sem som",
    )

    desmutar = (
        "tira do mudo",
        "tirar do mudo",
        "desmuta",
        "desmutar",
        "volta o som",
        "voltar o som",
    )

    if any(termo in texto_norm for termo in desmutar):
        return {
            "intent": "desmutar_volume",
            "parameters": {"acao": "desmutar"},
        }

    if any(termo in texto_norm for termo in mutar):
        return {
            "intent": "mutar_volume",
            "parameters": {"acao": "mutar"},
        }

    if any(termo in texto_norm for termo in aumentar):
        return {
            "intent": "aumentar_volume",
            "parameters": {"acao": "aumentar"},
        }

    if any(termo in texto_norm for termo in diminuir):
        return {
            "intent": "diminuir_volume",
            "parameters": {"acao": "diminuir"},
        }

    return None


# =========================================================
# DETECTOR RÁPIDO DE ATUALIZAÇÃO DE MEMÓRIA
# =========================================================

def detectar_atualizacao_memoria_rapida(texto):
    texto_original = str(texto or "").strip()
    texto_lower = normalizar_com_espacos(texto_original)

    # Remove conectores naturais do início.
    for prefixo in ("e ", "então ", "entao "):
        if texto_lower.startswith(prefixo):
            texto_original = texto_original[len(prefixo):].strip()
            texto_lower = normalizar_com_espacos(texto_original)
            break

    match_na_verdade = re.match(
        r"^(.+?)\s+na verdade\s+(?:agora\s+)?(?:e|eh|sao)\s+(.+)$",
        texto_lower,
        flags=re.IGNORECASE,
    )

    if match_na_verdade and texto_tem_marcador_pessoal(texto_lower):
        consulta = match_na_verdade.group(1).strip(" .,!?:;")
        novo_valor = match_na_verdade.group(2).strip(" .,!?:;")

        if consulta and novo_valor:
            return {
                "intent": "atualizar_memoria",
                "parameters": {
                    "consulta": consulta,
                    "novo_conteudo": (
                        f"{consulta} e {novo_valor}"
                    ),
                },
            }

    inicios = (
        "corrija ",
        "corrige ",
        "corrigir ",
        "atualize ",
        "atualiza ",
        "mude ",
        "muda ",
        "altere ",
        "altera ",
        "na verdade ",
    )

    inicio_usado = next(
        (
            inicio
            for inicio in inicios
            if texto_lower.startswith(inicio)
        ),
        None,
    )

    if not inicio_usado:
        return None

    restante = texto_original[len(inicio_usado):].strip()
    restante_norm = normalizar_com_espacos(restante)

    if not restante:
        return {
            "intent": "nao_entendi",
            "parameters": {},
        }

    if inicio_usado == "na verdade ":
        match = re.match(
            r"^(.+?)\s+(?:agora\s+)?(?:e|eh|sao)\s+(.+)$",
            restante_norm,
            flags=re.IGNORECASE,
        )

        if match and texto_tem_marcador_pessoal(restante_norm):
            consulta = match.group(1).strip(" .,!?:;")
            novo_valor = match.group(2).strip(" .,!?:;")

            if consulta and novo_valor:
                return {
                    "intent": "atualizar_memoria",
                    "parameters": {
                        "consulta": consulta,
                        "novo_conteudo": (
                            f"{consulta} e {novo_valor}"
                        ),
                    },
                }

    # Forma: "corrija X. Y"
    if "." in restante:
        primeira, segunda = restante.split(".", 1)
        consulta = primeira.strip(" .,!?:;")
        novo_conteudo = segunda.strip(" .,!?:;")

        if consulta and novo_conteudo:
            return {
                "intent": "atualizar_memoria",
                "parameters": {
                    "consulta": consulta,
                    "novo_conteudo": novo_conteudo,
                },
            }

    # Forma: "corrija X para Y"
    match = re.match(
        r"^(.+?)\s+para\s+(.+)$",
        restante,
        flags=re.IGNORECASE,
    )

    if match:
        consulta = match.group(1).strip(" .,!?:;")
        novo_valor = match.group(2).strip(" .,!?:;")

        if consulta and novo_valor:
            return {
                "intent": "atualizar_memoria",
                "parameters": {
                    "consulta": consulta,
                    "novo_conteudo": (
                        f"{consulta} e {novo_valor}"
                    ),
                },
            }

    return None


# =========================================================
# DETECTOR RÁPIDO PARA APAGAR MEMÓRIA
# =========================================================

def detectar_apagar_memoria_rapida(texto):
    texto_original = str(texto or "").strip()
    texto_lower = normalizar_com_espacos(texto_original)

    for prefixo in ("e ", "então ", "entao "):
        if texto_lower.startswith(prefixo):
            texto_original = texto_original[len(prefixo):].strip()
            texto_lower = normalizar_com_espacos(texto_original)
            break

    prefixos = (
        "esquece ",
        "esqueça ",
        "esqueca ",
        "apaga da memória ",
        "apaga da memoria ",
        "apague da memória ",
        "apague da memoria ",
        "remove da memória ",
        "remove da memoria ",
        "remova da memória ",
        "remova da memoria ",
    )

    for prefixo in prefixos:
        if texto_lower.startswith(prefixo):
            consulta = texto_original[len(prefixo):].strip()
            consulta = consulta.rstrip("?.!,").strip()

            if not consulta:
                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            return {
                "intent": "apagar_memoria",
                "parameters": {
                    "consulta": consulta,
                },
            }

    return None


# =========================================================
# DETECTOR RÁPIDO DE CONSULTA DE MEMÓRIA
# =========================================================

def detectar_consulta_memoria_rapida(texto):
    """
    Detecta consultas pessoais sobre a memoria persistente.
    Evita perguntas publicas/factuais sem marcador pessoal.
    """

    texto_norm = normalizar_com_espacos(texto)

    if not texto_norm:
        return None

    padroes_consulta = (
        r"^o que voce lembra (?:sobre|de|do|da) (.+)$",
        r"^o que eu te (?:falei|disse) sobre (.+)$",
        r"^lembra do que eu (?:falei|disse) sobre (.+)$",
        r"^voce lembra (?:qual e |qual |de |do |da |o |a )?(.+)$",
        r"^qual (?:e |eh )?(?:o |a |os |as )?(.+)$",
        r"^o que voce sabe sobre (.+)$",
    )

    for padrao in padroes_consulta:
        match = re.match(
            padrao,
            texto_norm,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        consulta = limpar_consulta_memoria(
            match.group(1)
        )

        if not consulta:
            return {
                "intent": "nao_entendi",
                "parameters": {},
            }

        consulta_eh_pessoal = (
            texto_tem_marcador_pessoal(texto_norm)
            or texto_norm.startswith("o que voce lembra")
            or texto_norm.startswith("o que eu te falei")
            or texto_norm.startswith("o que eu te disse")
            or texto_norm.startswith("lembra do que eu")
        )

        if not consulta_eh_pessoal:
            return None

        return {
            "intent": "consultar_memoria",
            "parameters": {
                "consulta": consulta,
            },
        }

    return None


def detectar_memoria_rapida(texto):
    """
    Detecta pedidos explicitos para salvar memoria.
    Inclui formas como: "lembre do nome da minha namorada, Evelyn".
    """

    texto_original = str(texto or "").strip()
    texto_norm = normalizar_com_espacos(texto_original)

    prefixos_que = (
        "lembra que ",
        "lembre que ",
        "guarda que ",
        "guarde que ",
        "memoriza que ",
        "memorize que ",
        "anota que ",
        "anote que ",
    )

    for prefixo in prefixos_que:
        if texto_norm.startswith(prefixo):
            conteudo = texto_original[len(prefixo):].strip()

            if not conteudo:
                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            return {
                "intent": "salvar_memoria",
                "parameters": {
                    "conteudo": conteudo,
                    "categoria": "notas",
                },
            }

    match = re.match(
        r"^(?:lembra|lembre|guarda|guarde|memoriza|memorize) "
        r"(?:do|da|de|o|a) (.+?)\s*,\s*(.+)$",
        texto_original,
        flags=re.IGNORECASE,
    )

    if match:
        assunto = match.group(1).strip(" .,!?:;")
        valor = match.group(2).strip(" .,!?:;")

        if assunto and valor:
            return {
                "intent": "salvar_memoria",
                "parameters": {
                    "conteudo": f"{assunto} e {valor}",
                    "categoria": "notas",
                },
            }

    return None


# =========================================================
# AI ROUTER
# =========================================================



def parece_continuacao_conversacional(texto, contexto_anterior):
    """
    Detecta complementos curtos que fazem sentido apenas junto do turno
    anterior, sem transformar comandos explícitos em conversa.

    A regra é estrutural: exige contexto recente, fala curta e ausência de
    verbos/formatos típicos de comando. Isso cobre correções e complementos
    como "queria comparar com Python" sem depender de uma lista de assuntos.
    """
    if not contexto_anterior:
        return False

    texto_norm = normalizar_com_espacos(texto)
    palavras = texto_norm.split()

    if not palavras or len(palavras) > 12:
        return False

    # Não rouba comandos explícitos do restante do router.
    comandos = (
        "abre", "abrir", "fecha", "feche", "fecho", "fechar",
        "toca", "toque", "tocar", "coloca", "coloque", "pausa",
        "pare", "para", "continua", "continue", "aumenta",
        "diminui", "muta", "desmuta", "pesquisa", "procura",
        "busca", "anota", "salva", "apaga", "esquece",
    )

    if palavras[0] in comandos:
        return False

    marcadores = (
        "eu queria", "queria", "eu quis", "quis", "quis dizer",
        "eu quis dizer", "na verdade", "era", "seria", "com ",
        "sobre ", "nesse caso", "isso", "esse", "essa", "ele",
        "ela", "e ", "mas ", "entao ",
    )

    return any(
        texto_norm == marcador.strip()
        or texto_norm.startswith(marcador)
        for marcador in marcadores
    )


def parece_pedido_comparacao(texto):
    """
    Detecta pedidos explícitos de comparação como conversa.

    Essa regra roda antes dos caminhos de memória para impedir que frases
    como "eu queria comparar Java com Python" sejam reinterpretadas como
    consulta de memória pelo fallback semântico.
    """
    texto_norm = normalizar_com_espacos(texto)

    if not texto_norm:
        return False

    padroes = (
        r"\bcomparar\b",
        r"\bcompare\b",
        r"\bcompara\b",
        r"\bcomparacao\b",
        r"\bdiferenca entre\b",
    )

    return any(re.search(padrao, texto_norm) for padrao in padroes)

class AIRouter:
    """Roteador híbrido: regras rápidas primeiro e LLM como fallback semântico."""

    def __init__(self, cliente_ollama=None):
        # Injeção opcional facilita testes sem alterar AIRouter() em produção.
        self._cliente_ollama = cliente_ollama if cliente_ollama is not None else ollama

        # Contexto conversacional curto e descartável.
        # Guarda somente as últimas falas do usuário para resolver referências
        # como "corrija para Cursor", "e quando?" ou "agora em 50".
        self._contexto_curto = deque(maxlen=4)

    @staticmethod
    def _nao_entendi():
        return {
            "intent": "nao_entendi",
            "parameters": {},
        }

    def _registrar_contexto(self, texto):
        texto = str(texto or "").strip()

        if not texto:
            return

        if self._contexto_curto and self._contexto_curto[-1] == texto:
            return

        self._contexto_curto.append(texto)

    def _obter_contexto_anterior(self):
        return list(self._contexto_curto)

    @staticmethod
    def _resolver_atualizacao_memoria_por_contexto(
        texto,
        contexto_anterior,
    ):
        """
        Resolve continuações curtas como "corrija para X" quando
        uma consulta de memória recente deixa claro o assunto.
        """

        texto_original = str(texto or "").strip()
        texto_norm = normalizar_com_espacos(texto_original)

        match = re.match(
            r"^(?:corrija|corrige|corrigir|mude|muda|altere|altera|"
            r"atualize|atualiza)(?:\s+isso)?\s+para\s+(.+)$",
            texto_norm,
            flags=re.IGNORECASE,
        )

        if not match:
            return None

        novo_valor = match.group(1).strip(" .,!?:;")

        if not novo_valor:
            return None

        for fala_anterior in reversed(contexto_anterior):
            consulta_anterior = detectar_consulta_memoria_rapida(
                fala_anterior
            )

            if (
                consulta_anterior
                and consulta_anterior.get("intent")
                == "consultar_memoria"
            ):
                consulta = str(
                    consulta_anterior.get(
                        "parameters",
                        {},
                    ).get(
                        "consulta",
                        "",
                    )
                ).strip()

                if consulta:
                    return {
                        "intent": "atualizar_memoria",
                        "parameters": {
                            "consulta": consulta,
                            "novo_conteudo": (
                                f"{consulta} é {novo_valor}"
                            ),
                        },
                    }

        return None

    @staticmethod
    def _montar_texto_com_contexto(texto, contexto_anterior):
        if not contexto_anterior:
            return texto

        historico = "\n".join(
            f"- {fala}"
            for fala in contexto_anterior
        )

        return (
            "Contexto recente da conversa:\n"
            f"{historico}\n\n"
            "Fala atual do usuário:\n"
            f"{texto}\n\n"
            "Use o contexto recente apenas para resolver referências "
            "implícitas da fala atual. Não invente assuntos que não "
            "apareçam no contexto ou na fala atual."
        )

    def interpretar(self, texto):
        texto = str(texto or "").strip()

        if not texto:
            return {
                "intent": "nao_entendi",
                "parameters": {},
            }

        contexto_anterior = self._obter_contexto_anterior()
        self._registrar_contexto(texto)

        if fala_depende_de_contexto(texto):
            texto_semantico = self._montar_texto_com_contexto(
                texto,
                contexto_anterior,
            )
        else:
            # Comandos explícitos atuais não devem herdar entidades antigas.
            # Isso evita, por exemplo, "para a música" reutilizar o nome de
            # uma faixa tocada anteriormente.
            texto_semantico = texto

        contexto_para_validacao = " ".join(
            [*contexto_anterior, texto]
        )

        atualizacao_contextual = (
            self._resolver_atualizacao_memoria_por_contexto(
                texto,
                contexto_anterior,
            )
        )

        if atualizacao_contextual:
            print("Router contextual: atualizar memória")
            return atualizacao_contextual

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA COMPARAÇÕES
        # -----------------------------------------------------

        if parece_pedido_comparacao(texto):
            print("Router rápido: comparação/conversa")
            return {
                "intent": "conversar",
                "parameters": {},
            }

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA ATUALIZAR MEMÓRIA
        # -----------------------------------------------------

        atualizacao_memoria = detectar_atualizacao_memoria_rapida(
            texto
        )

        if atualizacao_memoria:
            print("Router rápido: atualizar memória")
            return atualizacao_memoria

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA APAGAR MEMÓRIA
        # -----------------------------------------------------

        apagar_memoria = detectar_apagar_memoria_rapida(
            texto
        )

        if apagar_memoria:
            print("Router rápido: apagar memória")
            return apagar_memoria

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA CONSULTAR MEMÓRIA
        # -----------------------------------------------------

        consulta_memoria = detectar_consulta_memoria_rapida(
            texto
        )

        if consulta_memoria:
            print("Router rápido: consultar memória")
            return consulta_memoria

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA MEMÓRIA
        # -----------------------------------------------------

        memoria_rapida = detectar_memoria_rapida(texto)

        if memoria_rapida:
            print("Router rápido: salvar memória")
            return memoria_rapida

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA DECLARAÇÕES / PREFERÊNCIAS
        # -----------------------------------------------------

        declaracao_usuario = detectar_declaracao_usuario_rapida(
            texto
        )

        if declaracao_usuario:
            print("Router rápido: declaração/conversa")
            return declaracao_usuario

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA VOLUME
        # -----------------------------------------------------

        volume_rapido = detectar_volume_rapido(texto)

        if volume_rapido:
            print(
                "Router rápido: "
                f"{volume_rapido['intent']}"
            )

            return volume_rapido

        # -----------------------------------------------------
        # CAMINHO RÁPIDO PARA CONVERSA
        # -----------------------------------------------------

        if parece_continuacao_conversacional(texto, contexto_anterior):
            print("Router rápido: continuação de conversa")
            return {
                "intent": "conversar",
                "parameters": {},
            }

        if parece_conversa(texto):
            print(
                "Router rápido: conversa/pergunta"
            )

            return {
                "intent": "conversar",
                "parameters": {},
            }

        # -----------------------------------------------------
        # ROUTER SEMÂNTICO
        # -----------------------------------------------------

        inicio = time.perf_counter()

        try:
            if self._cliente_ollama is None:
                print("AI Router: Ollama não está disponível.")
                return self._nao_entendi()

            resposta = self._cliente_ollama.chat(
                model=MODELO_ROUTER,
                messages=[
                    {
                        "role": "system",
                        "content": SYSTEM_PROMPT_ROUTER,
                    },
                    {
                        "role": "user",
                        "content": texto_semantico,
                    },
                ],
                format="json",
                keep_alive="15m",
                options={
                    "temperature": 0.0,
                    "num_predict": 120,
                },
            )

            duracao = (
                time.perf_counter()
                - inicio
            )

            conteudo = resposta[
                "message"
            ][
                "content"
            ]

            dados = json.loads(
                conteudo
            )

            intent = dados.get(
                "intent"
            )

            parameters = dados.get(
                "parameters",
                {},
            )

            # -------------------------------------------------
            # INTENÇÃO INVÁLIDA
            # -------------------------------------------------

            if intent not in INTENTS_PERMITIDAS:
                print(
                    "AI Router retornou "
                    f"intenção inválida: {intent}"
                )

                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            # -------------------------------------------------
            # PARÂMETROS
            # -------------------------------------------------

            if not isinstance(
                parameters,
                dict,
            ):
                parameters = {}

            consulta = parameters.get(
                "consulta"
            )

            # -------------------------------------------------
            # PROTEÇÃO CONTRA OPERAÇÕES DE MEMÓRIA INVENTADAS
            # -------------------------------------------------

            if intent in {
                "salvar_memoria",
                "atualizar_memoria",
                "apagar_memoria",
            } and not texto_autoriza_operacao_memoria(texto, intent):
                print(
                    "AI Router bloqueou operação de memória sem "
                    f"pedido explícito: {intent}"
                )
                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            # -------------------------------------------------
            # PROTEÇÃO CONTRA ALUCINAÇÃO
            # -------------------------------------------------

            if (
                consulta
                and not consulta_esta_no_texto(
                    contexto_para_validacao,
                    consulta,
                )
            ):
                print(
                    "AI Router tentou inferir "
                    "uma consulta não presente "
                    f"no texto: {consulta}"
                )

                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            conteudo = parameters.get(
                "conteudo"
            )

            if (
                intent == "salvar_memoria"
                and conteudo
                and not consulta_esta_no_texto(
                    texto,
                    conteudo,
                )
            ):
                print(
                    "AI Router tentou salvar "
                    "conteudo nao presente no texto: "
                    f"{conteudo}"
                )

                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            novo_conteudo = parameters.get(
                "novo_conteudo"
            )

            if (
                intent == "atualizar_memoria"
                and novo_conteudo
                and not parametro_tem_palavra_do_texto(
                    texto,
                    novo_conteudo,
                )
            ):
                print(
                    "AI Router tentou atualizar "
                    "com conteudo sem base no texto: "
                    f"{novo_conteudo}"
                )

                return {
                    "intent": "nao_entendi",
                    "parameters": {},
                }

            # Nota não pode ganhar conteúdo inventado pelo modelo. Se o
            # usuário só disser "nota", preservamos a intenção e deixamos
            # commands.py perguntar o conteúdo.
            if intent == "criar_nota":
                texto_nota = str(
                    parameters.get("texto")
                    or parameters.get("conteudo")
                    or ""
                ).strip()

                if texto_nota and not parametro_tem_palavra_do_texto(
                    texto,
                    texto_nota,
                ):
                    print(
                        "AI Router descartou conteúdo de nota "
                        "sem base na fala atual."
                    )
                    parameters = {}
                elif texto_nota:
                    parameters = {"texto": texto_nota}

            # -------------------------------------------------
            # RESULTADO
            # -------------------------------------------------

            print(
                f"AI Router: {intent} | "
                f"{parameters} | "
                f"{duracao:.3f}s"
            )

            return {
                "intent": intent,
                "parameters": parameters,
            }

        except json.JSONDecodeError as erro:
            print(
                "AI Router retornou JSON inválido:",
                erro,
            )

            return {
                "intent": "nao_entendi",
                "parameters": {},
            }

        except Exception as erro:
            # O contrato público do router é sempre um dicionário.
            # Retornar None aqui fazia commands.py precisar lidar com dois
            # formatos diferentes justamente durante uma falha do Ollama.
            print(
                "Erro no AI Router:",
                erro,
            )

            return self._nao_entendi()