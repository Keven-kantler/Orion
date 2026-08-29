from ai_router import AIRouter
from memory_manager import MemoryManager
from memory_analyzer import MemoryAnalyzer
import os
import re
import threading
import subprocess
import webbrowser
from datetime import datetime
from urllib.parse import quote_plus

from config import PASTA_ORION
from intent_router import Intent, detectar_intencao, detectar_intencao_musical
from notes import criar_anotacao, ler_ultimas_anotacoes
from safety import acao_perigosa, resposta_acao_perigosa
from tv_controller import RokuTVController
from utils import contem_aproximado, normalizar_texto

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pyautogui
except ImportError:
    pyautogui = None

try:
    import pyperclip
except ImportError:
    pyperclip = None

try:
    from pycaw.pycaw import AudioUtilities
except ImportError:
    AudioUtilities = None


SPOTIFY_VARIANTES = [
    "spotify",
    "spote fire",
    "spot fire",
    "espotifi",
    "spotifi",
]


ai_router = AIRouter()
memory_manager = MemoryManager()
memory_analyzer = MemoryAnalyzer()
_tv_controller = None
# =========================================================
# MEMÓRIA AUTOMÁTICA
# =========================================================

def analisar_e_salvar_memoria_automatica(texto):
    """
    Analisa uma fala normal do usuário e salva somente
    informações duradouras consideradas úteis.
    """

    try:
        resultado = memory_analyzer.analisar(texto)
    except Exception as erro:
        # Memória automática é auxiliar: uma falha aqui nunca deve
        # impedir o Orion de responder ao usuário.
        print(f"Erro ao analisar memória automática: {erro}")
        return None

    if not isinstance(resultado, dict) or not resultado.get("salvar"):
        return None

    titulo = str(resultado.get("titulo", "")).strip()
    conteudo = str(resultado.get("conteudo", "")).strip()
    categoria = str(
        resultado.get("categoria", "notas")
    ).strip().lower()

    if not titulo or not conteudo:
        return None

    resultado_salvamento = memory_manager.salvar_memoria_inteligente(
        titulo=titulo,
        conteudo=conteudo,
        categoria=categoria,
    )

    if resultado_salvamento.get("salva"):
        print(
            "Memória automática salva: "
            f"{categoria} -> {titulo}"
        )
    elif resultado_salvamento.get("duplicada"):
        print("Memória automática não salva: duplicata.")

    return resultado_salvamento


def analisar_e_salvar_memoria_em_background(texto):
    """Executa a análise de memória sem bloquear a resposta do Orion."""

    thread = threading.Thread(
        target=analisar_e_salvar_memoria_automatica,
        args=(texto,),
        daemon=True,
        name="orion-memoria-automatica",
    )
    thread.start()


# =========================================================
# AÇÕES BÁSICAS
# =========================================================


def abrir_url(url, mensagem):
    print(f"Comando executado: {mensagem}")
    webbrowser.open(url)
    return mensagem


def abrir_app(nome, comando, mensagem):
    print(f"Comando executado: {mensagem}")

    try:
        if isinstance(comando, str) and comando.startswith("start:"):
            os.startfile(comando.replace("start:", "", 1))
        else:
            subprocess.Popen(comando, shell=False)

        return mensagem

    except Exception as erro:
        print(f"Erro ao abrir {nome}:", erro)
        return f"Não consegui abrir {nome}."


def abrir_spotify():
    try:
        # os.startfile lida diretamente com o protocolo spotify: no Windows
        # e, ao contrário de os.system("start ..."), permite detectar falha.
        os.startfile("spotify:")
        return "Abrindo Spotify."
    except Exception as erro:
        print(f"Não consegui abrir o app do Spotify: {erro}")
        return abrir_url(
            "https://open.spotify.com",
            "Abrindo Spotify.",
        )


def fechar_spotify():
    """Fecha apenas processos do Spotify no computador."""

    try:
        fechou = False

        if psutil is not None:
            for processo in psutil.process_iter(["name"]):
                nome = str(processo.info.get("name") or "").lower()

                if "spotify" in nome:
                    processo.terminate()
                    fechou = True
        else:
            resultado = subprocess.run(
                ["taskkill", "/IM", "Spotify.exe", "/F"],
                capture_output=True,
                text=True,
            )
            fechou = resultado.returncode == 0

        if fechou:
            return "Fechando Spotify."

        return "O Spotify já parece estar fechado."

    except Exception as erro:
        print(f"Erro ao fechar Spotify: {erro}")
        return "Não consegui fechar o Spotify."


def pesquisar_google(consulta):
    if not consulta:
        return "O que você quer pesquisar no Google?"

    return abrir_url(
        "https://www.google.com/search?q=" + quote_plus(consulta),
        "Pesquisando no Google.",
    )


def pesquisar_youtube(consulta):
    if not consulta:
        return "O que você quer pesquisar no YouTube?"

    return abrir_url(
        "https://www.youtube.com/results?search_query=" + quote_plus(consulta),
        "Pesquisando no YouTube.",
    )



# =========================================================
# ROKU TV
# =========================================================

APPS_STREAMING_TV = {
    "youtube", "netflix", "disney", "disney plus", "disney+",
    "prime video", "amazon prime", "amazon prime video",
    "max", "hbo max", "globoplay", "apple tv", "apple tv+",
    "paramount", "paramount+", "crunchyroll", "pluto tv", "twitch",
}


def _obter_tv():
    """Cria o controller somente quando um comando de TV for usado."""
    global _tv_controller

    if _tv_controller is None:
        _tv_controller = RokuTVController()

    return _tv_controller


def _extrair_app_tv(texto):
    texto_norm = normalizar_texto(texto)

    prefixos = (
        "abre ", "abra ", "abrir ",
        "coloca ", "coloque ", "bota ", "bote ",
    )

    restante = texto_norm
    for prefixo in prefixos:
        if restante.startswith(prefixo):
            restante = restante[len(prefixo):].strip()
            break
    else:
        return ""

    if restante.startswith(("o ", "a ")):
        restante = restante[2:].strip()

    for sufixo in (
        " na televisao", " na tv",
        " pra televisao", " pra tv",
        " para televisao", " para tv",
    ):
        if restante.endswith(sufixo):
            restante = restante[:-len(sufixo)].strip()
            break

    return restante.strip(" .,!?:;")


def processar_tv(texto):
    """
    Fast router da Roku.

    Streaming conhecido vai para a TV por padrão.
    Destino explícito PC/navegador nunca é interceptado.
    """
    texto_norm = normalizar_texto(texto).strip(" .,!?:;")

    if not texto_norm:
        return None

    if any(
        marcador in texto_norm
        for marcador in (" no pc", " no computador", " no navegador", " pelo navegador")
    ):
        return None

    fala_de_tv = (
        " tv" in f" {texto_norm}"
        or "televisao" in texto_norm
    )

    app = _extrair_app_tv(texto_norm)
    app_streaming = app in APPS_STREAMING_TV

    # Não inicializa o controller para frases sem relação com a TV.
    if not fala_de_tv and not app_streaming:
        return None

    try:
        tv = _obter_tv()
    except Exception as erro:
        print("Erro ao inicializar controle da TV:", erro)
        return "Não consegui acessar a configuração da TV."

    # Energia
    # IMPORTANTE: desligar vem antes de ligar.
    # "desligue a tv" contém "ligue a tv" como substring, então a ordem
    # anterior fazia o comando de desligar cair acidentalmente em ligar.
    comandos_desligar = (
        "desliga a tv", "desligar a tv", "desligue a tv",
        "desliga tv", "desligar tv", "desligue tv",
        "desliga a televisao", "desligar a televisao", "desligue a televisao",
    )

    if fala_de_tv and any(
        texto_norm == comando
        or texto_norm.startswith(comando + " ")
        for comando in comandos_desligar
    ):
        return tv.comando_desligar()

    comandos_ligar = (
        "liga a tv", "ligar a tv", "ligue a tv",
        "liga tv", "ligar tv", "ligue tv",
        "liga a televisao", "ligar a televisao", "ligue a televisao",
    )

    if fala_de_tv and any(
        texto_norm == comando
        or texto_norm.startswith(comando + " ")
        for comando in comandos_ligar
    ):
        return tv.comando_ligar()

    # Volume
    if fala_de_tv and "volume" in texto_norm:
        if any(t in texto_norm for t in ("aumenta", "aumente", "sobe", "mais volume")):
            return tv.comando_volume_up()
        if any(t in texto_norm for t in ("abaixa", "abaixe", "diminui", "diminua", "reduz")):
            return tv.comando_volume_down()

    if fala_de_tv and any(t in texto_norm for t in ("muta", "mute", "silencia", "sem som")):
        return tv.comando_mute()

    # Home
    if fala_de_tv and any(
        t in texto_norm
        for t in ("home", "tela inicial", "inicio da tv", "inicio da televisao")
    ):
        return tv.comando_home()

    # Navegação e mídia.
    if fala_de_tv:
        acoes = (
            (("vai pra cima", "vai para cima"), tv.up, "Indo para cima."),
            (("vai pra baixo", "vai para baixo"), tv.down, "Indo para baixo."),
            (("vai pra esquerda", "vai para esquerda", "esquerda"), tv.left, "Indo para a esquerda."),
            (("vai pra direita", "vai para direita", "direita"), tv.right, "Indo para a direita."),
            (("seleciona", "selecionar", "confirma", " ok"), tv.select, "Selecionado."),
            (("volta", "voltar"), tv.back, "Voltando."),
            (("pausa", "pause", "play", "continua"), tv.play_pause, "Controlei a reprodução."),
            (("avanca", "avançar", "avancar"), tv.forward, "Avançando."),
            (("retrocede", "retroceder", "volta o video"), tv.rewind, "Retrocedendo."),
        )

        for termos, acao, mensagem in acoes:
            if any(termo in texto_norm for termo in termos):
                if not tv.esta_ligada():
                    return "A TV está desligada."
                try:
                    acao()
                    return mensagem
                except Exception as erro:
                    print("Erro ao controlar navegação da TV:", erro)
                    return "Não consegui controlar a TV."

    # O controller cuida de ligar/aguardar a TV antes de abrir o app.
    if app and (fala_de_tv or app_streaming):
        return tv.comando_abrir_app(app)

    return None


# =========================================================
# CONTROLE DO SISTEMA
# =========================================================


def controlar_volume_sistema(acao):
    print(f"Intenção detectada: volume do sistema - {acao}")

    try:
        if AudioUtilities:
            dispositivo = AudioUtilities.GetSpeakers()
            volume = dispositivo.EndpointVolume

            if acao == "aumentar":
                atual = volume.GetMasterVolumeLevelScalar()

                volume.SetMasterVolumeLevelScalar(
                    min(1.0, atual + 0.1),
                    None,
                )

                return "Aumentei o volume."

            if acao == "diminuir":
                atual = volume.GetMasterVolumeLevelScalar()

                volume.SetMasterVolumeLevelScalar(
                    max(0.0, atual - 0.1),
                    None,
                )

                return "Diminuí o volume."

            if acao == "mutar":
                volume.SetMute(
                    1,
                    None,
                )

                return "Volume mutado."

            if acao == "desmutar":
                volume.SetMute(
                    0,
                    None,
                )

                return "Volume desmutado."

        if pyautogui:
            teclas = {
                "aumentar": "volumeup",
                "diminuir": "volumedown",
                "mutar": "volumemute",
                "desmutar": "volumemute",
            }

            tecla = teclas.get(acao)

            if not tecla:
                return "Não reconheci esse controle de volume."

            pyautogui.press(tecla)

            return "Controlei o volume."

        return "Não encontrei suporte para controlar volume."

    except Exception as erro:
        print(
            "Erro ao controlar volume:",
            erro,
        )

        # Último fallback: usa as teclas multimídia do Windows.
        try:
            if pyautogui:
                teclas = {
                    "aumentar": "volumeup",
                    "diminuir": "volumedown",
                    "mutar": "volumemute",
                    "desmutar": "volumemute",
                }

                tecla = teclas.get(acao)

                if tecla:
                    pyautogui.press(tecla)
                    return "Controlei o volume."

        except Exception as erro_fallback:
            print(
                "Erro no fallback de volume:",
                erro_fallback,
            )

        return "Não consegui controlar o volume."

def listar_programas_abertos():
    print("Comando executado: listar programas abertos")

    try:
        if psutil:
            nomes = sorted(
                {
                    processo.info["name"]
                    for processo in psutil.process_iter(["name"])
                    if processo.info.get("name")
                }
            )
        else:
            resultado = subprocess.run(
                ["tasklist"],
                capture_output=True,
                text=True,
                encoding="cp850",
                errors="ignore",
            )
            nomes = [
                linha.split()[0]
                for linha in resultado.stdout.splitlines()[3:25]
                if linha.strip()
            ]

        if not nomes:
            return "Não consegui identificar programas abertos."

        return "Alguns programas abertos são: " + ", ".join(nomes[:8]) + "."

    except Exception as erro:
        print("Erro ao listar programas:", erro)
        return "Não consegui listar os programas abertos."


def copiar_texto_atual():
    if not pyautogui or not pyperclip:
        return "Não tenho suporte de cópia disponível agora."

    try:
        pyautogui.hotkey("ctrl", "c")
        texto = pyperclip.paste()

        if texto:
            return "Copiei o texto selecionado."

        return "Não encontrei texto selecionado."

    except Exception as erro:
        print("Erro ao copiar texto:", erro)
        return "Não consegui copiar o texto."


# =========================================================
# SPOTIFY
# =========================================================


def processar_spotify(texto, spotify):
    texto_norm = normalizar_texto(texto)
    fala_de_spotify = contem_aproximado(
        texto_norm,
        SPOTIFY_VARIANTES,
    )

    # Comandos explícitos do aplicativo têm prioridade sobre contexto musical.
    if fala_de_spotify and (
        re.search(r"\bfech(?:a|e|o|ar|ando)?\b", texto_norm)
        or re.search(r"\bencerr(?:a|e|o|ar|ando)?\b", texto_norm)
    ):
        print("Intenção detectada: fechar Spotify")
        return fechar_spotify()

    # Funções que ainda não fazem parte do intent_router musical.
    if (
        "que musica esta tocando" in texto_norm
        or "qual musica esta tocando" in texto_norm
        or "o que esta tocando" in texto_norm
    ):
        print("Intenção detectada: estado Spotify")
        return spotify.estado_spotify()

    if "volume do spotify" in texto_norm:
        if "aumenta" in texto_norm or "aumentar" in texto_norm:
            return spotify.volume_spotify(70)

        if "abaixa" in texto_norm or "diminu" in texto_norm:
            return spotify.volume_spotify(35)

    intencao_musical = detectar_intencao_musical(texto_norm)

    if intencao_musical:
        resposta = executar_intencao_musical(
            intencao_musical,
            spotify,
        )

        if resposta:
            return resposta

    # O router geral só é executado depois de processar_spotify.
    # Por isso, a abertura direta do Spotify permanece aqui.
    if fala_de_spotify and ("abrir" in texto_norm or "abre" in texto_norm):
        print("Intenção detectada: abrir Spotify")
        return abrir_spotify()

    return None


def executar_intencao_musical(intencao, spotify):
    acoes_reproducao = {
        "proxima_musica": spotify.proxima_musica,
        "musica_anterior": spotify.musica_anterior,
        "pausar_musica": spotify.pausar_spotify,
        "continuar_musica": spotify.continuar_spotify,
    }

    acao = acoes_reproducao.get(intencao.nome)

    if acao:
        print(f"Intenção detectada: {intencao.nome}")
        return acao()

    if intencao.nome != "tocar_musica":
        return None

    parametros = intencao.parametros
    tipo = parametros.get("tipo")
    consulta = parametros.get("consulta", "")

    print(
        "Intenção detectada: "
        f"música no Spotify - {tipo} -> {consulta}"
    )

    if tipo == "generico":
        return spotify.continuar_spotify()

    if tipo == "artista":
        return spotify.tocar_artista(consulta)

    return spotify.tocar_musica(consulta)


# =========================================================
# EXECUÇÃO DE INTENÇÕES GERAIS
# =========================================================


def executar_intencao(intencao):
    print(f"Intenção detectada: {intencao.nome}")
    parametros = intencao.parametros

    if intencao.nome == "abrir_spotify":
        return abrir_spotify()

    if intencao.nome == "pesquisar_youtube":
        return pesquisar_youtube(parametros.get("consulta", ""))

    if intencao.nome == "pesquisar_google":
        return pesquisar_google(parametros.get("consulta", ""))

    if intencao.nome == "abrir_site":
        return executar_abrir_site(parametros.get("site"))

    if intencao.nome == "abrir_aplicativo":
        return executar_abrir_aplicativo(parametros.get("aplicativo"))

    if intencao.nome in {
        "ligar_tv", "desligar_tv",
        "aumentar_volume_tv", "diminuir_volume_tv", "mutar_tv",
        "tv_home", "tv_cima", "tv_baixo", "tv_esquerda", "tv_direita",
        "tv_selecionar", "tv_voltar", "tv_play_pause",
        "tv_avancar", "tv_retroceder", "abrir_app_tv",
    }:
        try:
            tv = _obter_tv()
        except Exception as erro:
            print("Erro ao inicializar controle da TV:", erro)
            return "Não consegui acessar a configuração da TV."

        acoes_tv = {
            "ligar_tv": tv.comando_ligar,
            "desligar_tv": tv.comando_desligar,
            "aumentar_volume_tv": tv.comando_volume_up,
            "diminuir_volume_tv": tv.comando_volume_down,
            "mutar_tv": tv.comando_mute,
            "tv_home": tv.comando_home,
        }

        if intencao.nome == "abrir_app_tv":
            nome_app = str(parametros.get("aplicativo", "")).strip()
            if not nome_app:
                return "Qual aplicativo você quer abrir na TV?"
            return tv.comando_abrir_app(nome_app)

        if intencao.nome in acoes_tv:
            return acoes_tv[intencao.nome]()

        if not tv.esta_ligada():
            return "A TV está desligada."

        navegacao_tv = {
            "tv_cima": (tv.up, "Indo para cima."),
            "tv_baixo": (tv.down, "Indo para baixo."),
            "tv_esquerda": (tv.left, "Indo para a esquerda."),
            "tv_direita": (tv.right, "Indo para a direita."),
            "tv_selecionar": (tv.select, "Selecionado."),
            "tv_voltar": (tv.back, "Voltando."),
            "tv_play_pause": (tv.play_pause, "Controlei a reprodução."),
            "tv_avancar": (tv.forward, "Avançando."),
            "tv_retroceder": (tv.rewind, "Retrocedendo."),
        }

        acao, mensagem = navegacao_tv[intencao.nome]
        try:
            acao()
            return mensagem
        except Exception as erro:
            print("Erro ao controlar TV:", erro)
            return "Não consegui controlar a TV."

    if intencao.nome in {
        "aumentar_volume",
        "diminuir_volume",
        "mutar_volume",
        "desmutar_volume",
    }:
        acoes_volume = {
            "aumentar_volume": "aumentar",
            "diminuir_volume": "diminuir",
            "mutar_volume": "mutar",
            "desmutar_volume": "desmutar",
        }

        acao = parametros.get("acao") or acoes_volume.get(intencao.nome)
        return controlar_volume_sistema(acao)

    if intencao.nome == "falar_hora_atual":
        return f"Agora são {datetime.now().strftime('%H:%M')}."

    if intencao.nome == "criar_nota":
        return criar_anotacao(parametros.get("texto", ""))

    if intencao.nome == "ler_notas":
        return ler_ultimas_anotacoes()

    if intencao.nome == "salvar_memoria":
        conteudo = str(
            parametros.get("conteudo", "")
        ).strip()

        categoria = str(
            parametros.get("categoria", "notas")
        ).strip().lower()

        categorias_permitidas = {
            "perfil",
            "projetos",
            "conhecimento",
            "ideias",
            "notas",
            "conversas",
        }

        if categoria not in categorias_permitidas:
            categoria = "notas"

        if not conteudo:
            return "O que você quer que eu lembre?"

        # Título curto e legível para aparecer bem no Obsidian.
        titulo = conteudo[:60].strip()

        if len(conteudo) > 60:
            titulo = titulo.rstrip(" ,.;:-") + "..."

        resultado_salvamento = memory_manager.salvar_memoria_inteligente(
            titulo=titulo,
            conteudo=conteudo,
            categoria=categoria,
        )

        if resultado_salvamento.get("salva"):
            print(
                "Memória persistente salva: "
                f"{categoria} -> {conteudo}"
            )
            return "Vou lembrar disso."

        if resultado_salvamento.get("duplicada"):
            return "Eu já lembrava disso."

        return "Não consegui salvar essa memória."

    return None


def executar_abrir_aplicativo(aplicativo):
    apps = {
        "discord": lambda: abrir_app(
            "Discord",
            "start:discord:",
            "Abrindo Discord.",
        ),
        "steam": lambda: abrir_app(
            "Steam",
            "start:steam:",
            "Abrindo Steam.",
        ),
        "calculadora": lambda: abrir_app(
            "calculadora",
            ["calc.exe"],
            "Abrindo a calculadora.",
        ),
        "bloco_de_notas": lambda: abrir_app(
            "bloco de notas",
            ["notepad.exe"],
            "Abrindo o bloco de notas.",
        ),
        "explorador_arquivos": lambda: abrir_app(
            "explorador de arquivos",
            ["explorer.exe"],
            "Abrindo o explorador de arquivos.",
        ),
        "pasta_orion": lambda: abrir_app(
            "pasta do Orion",
            ["explorer.exe", PASTA_ORION],
            "Abrindo a pasta do Orion.",
        ),
    }

    acao = apps.get(aplicativo)
    return acao() if acao else None


def executar_abrir_site(site):
    sites = {
        "youtube": (
            "https://youtube.com",
            "Abrindo YouTube.",
        ),
        "google": (
            "https://google.com",
            "Abrindo Google.",
        ),
    }

    if site in sites:
        url, mensagem = sites[site]
        return abrir_url(url, mensagem)

    if site:
        if site.startswith(("http://", "https://")):
            url = site
        else:
            url = "https://" + site

        return abrir_url(url, f"Abrindo {site}.")

    return None


# =========================================================
# ROTEAMENTO PRINCIPAL
# =========================================================


def _parece_pedido_memoria(texto):
    """
    Retorna True somente quando há indícios claros de uma operação
    explícita de memória. Isso evita chamar o AI Router antes dos
    fast routers para toda frase recebida.

    A decisão final continua pertencendo ao AIRouter; esta função
    apenas decide se vale consultá-lo com prioridade.
    """
    texto_norm = normalizar_texto(texto)

    termos = (
        "lembre",
        "lembra",
        "lembrar",
        "memorize",
        "memoriza",
        "guarde",
        "guarda",
        "salve na memoria",
        "salva na memoria",
        "minha memoria",
        "suas memorias",
        "o que voce lembra",
        "voce lembra",
        "corrija",
        "corrige",
        "atualize",
        "atualiza",
        "esqueca",
        "esquece",
        "apague da memoria",
        "apaga da memoria",
    )

    return any(termo in texto_norm for termo in termos)


def processar_comando_pc(texto):
    texto_norm = normalizar_texto(texto)

    if acao_perigosa(texto_norm):
        print("Intenção perigosa detectada; bloqueada.")
        return resposta_acao_perigosa()

    intencao = detectar_intencao(texto_norm)

    if intencao:
        return executar_intencao(intencao)

    # Fallbacks ainda não migrados para o intent_router.
    if "navegador" in texto_norm:
        return abrir_url(
            "https://google.com",
            "Abrindo o navegador.",
        )

    if (
        "desmutar volume" in texto_norm
        or "desmuta o volume" in texto_norm
    ):
        return controlar_volume_sistema("desmutar")

    if (
        "programas abertos" in texto_norm
        or "quais programas estao abertos" in texto_norm
    ):
        return listar_programas_abertos()

    if "copiar texto" in texto_norm or "copia o texto" in texto_norm:
        return copiar_texto_atual()

    return None


def responder_fala_social_rapida(texto):
    """Responde cortesias simples sem gastar uma chamada ao AI Router."""
    texto_norm = normalizar_texto(texto)
    texto_norm = re.sub(r"[^\w\s]+", " ", texto_norm)
    texto_norm = re.sub(r"\s+", " ", texto_norm).strip()

    if texto_norm.endswith(" orion"):
        texto_norm = texto_norm[:-6].strip()

    respostas = {
        "obrigado": "De nada.",
        "obrigada": "De nada.",
        "muito obrigado": "De nada.",
        "muito obrigada": "De nada.",
        "valeu": "Tamo junto.",
        "brigado": "De nada.",
        "brigada": "De nada.",
        "boa noite": "Boa noite.",
        "bom dia": "Bom dia.",
        "boa tarde": "Boa tarde.",
        "ate mais": "Até mais.",
        "falou": "Falou.",
    }

    return respostas.get(texto_norm)


def processar_texto_usuario(texto, brain, spotify):
    texto = texto.strip()

    if not texto:
        return "Não ouvi nada útil."

    print(f"Texto recebido: {texto}")

    # =====================================================
    # 0. MEMÓRIA - PRIORIDADE ALTA
    # =====================================================
    #
    # Pedidos explícitos para lembrar algo precisam ser
    # analisados antes do Spotify. Isso evita frases como
    # "me lembre que..." serem confundidas com pedidos
    # de música pelo fast router musical.
    # =====================================================

    # O AI Router só ganha prioridade quando a frase realmente parece
    # ser uma operação de memória. Antes ele era chamado para TODA fala,
    # inclusive comandos simples de Spotify/PC, adicionando latência e
    # criando uma segunda decisão antes dos fast routers.
    resultado_memoria = None

    if _parece_pedido_memoria(texto):
        resultado_memoria = ai_router.interpretar(texto)

    if (
        resultado_memoria
        and resultado_memoria.get("intent") == "salvar_memoria"
    ):
        print(
            "Pedido de memória detectado antes dos outros routers."
        )

        intencao_memoria = Intent(
            "salvar_memoria",
            resultado_memoria.get("parameters", {}),
        )

        return executar_intencao(
            intencao_memoria
        )

    if (
        resultado_memoria
        and resultado_memoria.get("intent") == "consultar_memoria"
    ):
        print(
            "Consulta de memória detectada antes dos outros routers."
        )

        parametros_memoria = resultado_memoria.get(
            "parameters",
            {},
        )

        consulta = str(
            parametros_memoria.get("consulta", "")
        ).strip()

        if not consulta:
            return "O que você quer que eu tente lembrar?"

        memorias = memory_manager.buscar_memorias(
            consulta,
            limite=5,
        )

        if not memorias:
            print(
                f"Nenhuma memória encontrada para: {consulta}"
            )
            return "Não encontrei nenhuma memória relacionada a isso."

        print(
            f"Memórias encontradas para '{consulta}': "
            f"{len(memorias)}"
        )

        for memoria in memorias:
            print(
                " - "
                f"{memoria.get('titulo')} "
                f"| categoria={memoria.get('categoria')} "
                f"| score={memoria.get('score')}"
            )

        return brain.responder_com_memoria(
            texto,
            memorias,
        )

    if (
        resultado_memoria
        and resultado_memoria.get("intent") == "atualizar_memoria"
    ):
        print(
            "Atualização de memória detectada antes dos outros routers."
        )

        parametros_memoria = resultado_memoria.get(
            "parameters",
            {},
        )

        consulta = str(
            parametros_memoria.get("consulta", "")
        ).strip()

        novo_conteudo = str(
            parametros_memoria.get("novo_conteudo", "")
        ).strip()

        if not consulta or not novo_conteudo:
            return "Diga qual memória devo corrigir e qual é a informação correta."

        resultado_atualizacao = memory_manager.atualizar_memoria(
            consulta=consulta,
            novo_conteudo=novo_conteudo,
        )

        if resultado_atualizacao.get("atualizada"):
            brain.limpar_historico()
            return "Corrigi essa memória."

        return "Não encontrei essa memória para corrigir."

    if (
        resultado_memoria
        and resultado_memoria.get("intent") == "apagar_memoria"
    ):
        print(
            "Pedido para apagar memória detectado antes dos outros routers."
        )

        parametros_memoria = resultado_memoria.get(
            "parameters",
            {},
        )

        consulta = str(
            parametros_memoria.get("consulta", "")
        ).strip()

        if not consulta:
            return "Qual memória você quer que eu esqueça?"

        resultado_exclusao = memory_manager.apagar_memoria(
            consulta=consulta,
        )

        if resultado_exclusao.get("apagada"):
            brain.limpar_historico()
            return "Esqueci essa informação."

        return "Não encontrei essa memória para apagar."

    # =====================================================
    # 1. FAST ROUTER - TV
    # =====================================================

    resposta_tv = processar_tv(texto)

    if resposta_tv:
        return resposta_tv

    # Se a fala menciona explicitamente TV/televisão, mas o fast router
    # não reconheceu uma ação segura, não deixa Spotify/PC/AI executar
    # uma interpretação não relacionada por causa de erro de transcrição.
    texto_norm_tv = normalizar_texto(texto)
    menciona_tv = (
        " tv" in f" {texto_norm_tv}"
        or "televisao" in texto_norm_tv
    )

    if menciona_tv:
        intencao_tv = detectar_intencao(texto)
        eh_conversa_sobre_tv = (
            intencao_tv is not None
            and intencao_tv.nome == "conversar"
        )

        if not eh_conversa_sobre_tv:
            print("Comando relacionado à TV não reconhecido com segurança.")
            return "Não entendi o comando da TV. Pode repetir?"

    # =====================================================
    # 2. FAST ROUTER - SPOTIFY
    # =====================================================

    resposta_spotify = processar_spotify(
        texto,
        spotify,
    )

    if resposta_spotify:
        return resposta_spotify

    # =====================================================
    # 3. FAST ROUTER - PC / SISTEMA
    # =====================================================

    resposta_pc = processar_comando_pc(texto)

    if resposta_pc:
        return resposta_pc

    # =====================================================
    # 3.5 CORTESIAS / FALAS SOCIAIS SIMPLES
    # =====================================================

    resposta_social = responder_fala_social_rapida(texto)

    if resposta_social:
        print("Fast Router: fala social")
        return resposta_social

    # =====================================================
    # 4. AI ROUTER - LINGUAGEM NATURAL
    # =====================================================

    print("Fast Router não reconheceu. Consultando AI Router...")

    resultado_ai = resultado_memoria

    if not resultado_ai:
        resultado_ai = ai_router.interpretar(texto)

    if resultado_ai:
        nome_intencao = resultado_ai.get("intent")
        parametros = resultado_ai.get("parameters", {})

        if nome_intencao == "nao_entendi":
           print("AI Router: comando ambíguo ou incompreensível")
           return "Não entendi direito. Pode repetir?"

        if nome_intencao == "conversar":
            print("AI Router decidiu: conversa")

            resposta = brain.responder(texto)

            analisar_e_salvar_memoria_em_background(
                texto
            )

            return resposta

        # Trata operações de memória reconhecidas somente nesta segunda
        # passagem do AI Router. Sem isso, "consultar_memoria" chegava
        # a executar_intencao(), que não implementa essa intenção.
        if nome_intencao == "consultar_memoria":
            consulta = str(
                parametros.get("consulta", "")
            ).strip()

            if not consulta:
                return "O que você quer que eu tente lembrar?"

            memorias = memory_manager.buscar_memorias(
                consulta,
                limite=5,
            )

            if not memorias:
                print(
                    f"Nenhuma memória encontrada para: {consulta}"
                )
                return "Não encontrei nenhuma memória relacionada a isso."

            print(
                f"Memórias encontradas para '{consulta}': "
                f"{len(memorias)}"
            )

            for memoria in memorias:
                print(
                    " - "
                    f"{memoria.get('titulo')} "
                    f"| categoria={memoria.get('categoria')} "
                    f"| score={memoria.get('score')}"
                )

            return brain.responder_com_memoria(
                texto,
                memorias,
            )

        if nome_intencao == "atualizar_memoria":
            consulta = str(
                parametros.get("consulta", "")
            ).strip()
            novo_conteudo = str(
                parametros.get("novo_conteudo", "")
            ).strip()

            if not consulta or not novo_conteudo:
                return (
                    "Diga qual memória devo corrigir "
                    "e qual é a informação correta."
                )

            resultado_atualizacao = memory_manager.atualizar_memoria(
                consulta=consulta,
                novo_conteudo=novo_conteudo,
            )

            if resultado_atualizacao.get("atualizada"):
                brain.limpar_historico()
                return "Corrigi essa memória."

            return "Não encontrei essa memória para corrigir."

        if nome_intencao == "apagar_memoria":
            consulta = str(
                parametros.get("consulta", "")
            ).strip()

            if not consulta:
                return "Qual memória você quer que eu esqueça?"

            resultado_exclusao = memory_manager.apagar_memoria(
                consulta=consulta,
            )

            if resultado_exclusao.get("apagada"):
                brain.limpar_historico()
                return "Esqueci essa informação."

            return "Não encontrei essa memória para apagar."

        intencao = Intent(
            nome_intencao,
            parametros,
        )

        intencoes_musicais = {
            "tocar_musica",
            "proxima_musica",
            "musica_anterior",
            "pausar_musica",
            "continuar_musica",
        }

        if nome_intencao in intencoes_musicais:
            resposta = executar_intencao_musical(
                intencao,
                spotify,
            )

            if resposta:
                return resposta

        resposta = executar_intencao(intencao)

        if resposta:
            return resposta

    # =====================================================
    # 5. FALLBACK FINAL - IA CONVERSACIONAL
    # =====================================================

    print("AI Router não conseguiu decidir. Usando IA local.")

    resposta = brain.responder(texto)

    analisar_e_salvar_memoria_em_background(
        texto
    )

    return resposta