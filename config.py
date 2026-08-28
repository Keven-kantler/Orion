import os
from pathlib import Path

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None


# Raiz real do projeto. Pode ser sobrescrita por ORION_HOME no .env/sistema.
_DIRETORIO_CONFIG = Path(__file__).resolve().parent

if load_dotenv:
    # Carrega sempre o .env da pasta do Orion, independentemente do diretório
    # em que o programa foi iniciado.
    load_dotenv(dotenv_path=_DIRETORIO_CONFIG / ".env")
else:
    print(
        "Aviso: python-dotenv não instalado. "
        "O arquivo .env não será carregado automaticamente."
    )


def _env_float(nome, padrao):
    valor = os.getenv(nome, "").strip()
    if not valor:
        return padrao

    try:
        return float(valor)
    except ValueError:
        print(f"Aviso: {nome} inválido ({valor}). Usando {padrao}.")
        return padrao


def _env_int(nome, padrao):
    valor = os.getenv(nome, "").strip()
    if not valor:
        return padrao

    try:
        return int(valor)
    except ValueError:
        print(f"Aviso: {nome} inválido ({valor}). Usando {padrao}.")
        return padrao


# Caminhos
# Mantém compatibilidade com C:\Orion, mas deixa o projeto portátil.
PASTA_ORION = os.getenv("ORION_HOME", str(_DIRETORIO_CONFIG)).strip() or str(_DIRETORIO_CONFIG)
PASTA_ORION = os.path.abspath(os.path.expanduser(PASTA_ORION))
PASTA_NOTES = os.path.join(PASTA_ORION, "notes")


# Áudio e ativação
TAXA_AUDIO = 16000
TEMPO_BLOCO_AUDIO = 0.25
INTERVALO_DEBOUNCE_TECLA = 0.5

AUDIO_INPUT_DEVICE = os.getenv("AUDIO_INPUT_DEVICE", "").strip()
MODO_ATIVACAO = os.getenv("MODO_ATIVACAO", "manual").strip().lower()
WAKEWORD_ENGINE = os.getenv("WAKEWORD_ENGINE", "openwakeword").strip().lower()

OPENWAKEWORD_MODEL = os.getenv("OPENWAKEWORD_MODEL", "hey_jarvis").strip()
OPENWAKEWORD_THRESHOLD = _env_float("OPENWAKEWORD_THRESHOLD", 0.15)
OPENWAKEWORD_BLOCK_SAMPLES = _env_int("OPENWAKEWORD_BLOCK_SAMPLES", 1280)
WAKEWORD_COOLDOWN_SEGUNDOS = _env_float("WAKEWORD_COOLDOWN_SEGUNDOS", 3.0)

SILENCIO_LIMIAR_AUDIO = _env_float("SILENCIO_LIMIAR_AUDIO", 0.005)
SILENCIO_SEGUNDOS_AUTO_STOP = _env_float("SILENCIO_SEGUNDOS_AUTO_STOP", 0.6)
GRAVACAO_AUTO_MAX_SEGUNDOS = _env_float("GRAVACAO_AUTO_MAX_SEGUNDOS", 6.0)
GRAVACAO_AUTO_MIN_SEGUNDOS = _env_float("GRAVACAO_AUTO_MIN_SEGUNDOS", 0.6)


# Modelos
MODELO_WHISPER = "medium"
MODELO_IA = "qwen2.5:7b"
MODELO_ROUTER = "qwen2.5:1.5b"

WHISPER_INITIAL_PROMPT = (
    "Português do Brasil. O usuário pode falar comandos de computador, perguntas gerais, "
    "nomes de músicas, artistas, jogos, animes, personagens, aplicativos e sites. "
    "Exemplos: abrir Spotify, tocar a música do Tony Stark, tocar AC/DC, tocar Back in Black, "
    "pesquisar no Google, pesquisar no YouTube, abrir Discord, abrir Steam, Satoru Gojo, "
    "Jujutsu Kaisen, Counter-Strike, Homem de Ferro, Tony Stark."
)

OLLAMA_SYSTEM_PROMPT = (
    "Você é o Orion, um assistente pessoal local no PC do usuário. "
    "Responda exclusivamente em português do Brasil. "
    "Fale como em uma conversa natural, não como um chatbot escrevendo um texto. "
    "Normalmente responda em uma ou duas frases, mas explique mais quando a pergunta realmente exigir. "
    "Vá direto ao ponto. "
    "Evite começar respostas com expressões artificiais como 'Claro!', 'Com certeza!', "
    "'Certamente!' ou 'Posso ajudar com isso'. "
    "Não repita a pergunta do usuário antes de responder. "
    "Não termine toda resposta oferecendo ajuda novamente. "
    "Use naturalmente o contexto da conversa quando ele for relevante. "
    "Não invente fatos. "
    "Se não tiver certeza, diga que não tem certeza. "
    "Para fatos específicos, personagens, animes, jogos, tecnologia, pessoas, datas e notícias, "
    "responda com cautela. "
    "Se precisar de informação atualizada, diga que precisa consultar a internet. "
    "Nunca responda em outro idioma."
)


# Spotify
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "").strip()
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "").strip()
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI",
    "http://127.0.0.1:8888/callback",
).strip()

SPOTIFY_SCOPES = " ".join([
    "user-read-playback-state",
    "user-modify-playback-state",
    "user-read-currently-playing",
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-library-read",
])

# Roku TV
ROKU_TV_IP = os.getenv("ROKU_TV_IP", "").strip()
ROKU_TV_PORT = _env_int("ROKU_TV_PORT", 8060)