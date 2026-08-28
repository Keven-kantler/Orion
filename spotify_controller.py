import os
import re
import time
import unicodedata
import webbrowser
from difflib import SequenceMatcher
from pathlib import Path
from urllib.parse import quote_plus

from config import (
    PASTA_ORION,
    SPOTIFY_CLIENT_ID,
    SPOTIFY_CLIENT_SECRET,
    SPOTIFY_REDIRECT_URI,
    SPOTIFY_SCOPES,
)

try:
    import spotipy
    from spotipy.exceptions import SpotifyException
    from spotipy.oauth2 import SpotifyOAuth
except ImportError:
    spotipy = None
    SpotifyOAuth = None

    class SpotifyException(Exception):
        """Fallback local apenas para manter o módulo importável sem Spotipy."""

        http_status = None
        code = None
        headers = {}


class SpotifyController:
    def __init__(self, cliente_spotify=None):
        """
        Controlador do Spotify usado pelo Orion.

        `cliente_spotify` existe para testes e não altera o uso normal:
            SpotifyController()

        Quando um cliente é injetado, a etapa OAuth é ignorada.
        """
        self.sp = None
        self._auth = None

        if cliente_spotify is not None:
            self.sp = cliente_spotify
            self._configurado = True
            return

        self._configurado = bool(
            SPOTIFY_CLIENT_ID
            and SPOTIFY_CLIENT_SECRET
            and spotipy
            and SpotifyOAuth
        )

        if not spotipy:
            print(
                "Aviso: spotipy não instalado. "
                "Spotify avançado ficará em fallback."
            )
            return

        if not self._configurado:
            print(
                "Aviso: Spotify API não configurada. "
                "Preencha .env para controle avançado."
            )
            return

        try:
            cache_path = (
                Path(PASTA_ORION)
                / ".spotify_cache"
            )

            self._auth = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=SPOTIFY_SCOPES,
                open_browser=True,
                cache_path=str(cache_path),
            )

            self.sp = spotipy.Spotify(
                auth_manager=self._auth
            )

        except Exception as erro:
            print(
                "Aviso: não consegui inicializar Spotify API:",
                erro,
            )
            self.sp = None

    # =========================================================
    # ESTADO / FALLBACK
    # =========================================================

    def spotify_configurado(self):
        return self.sp is not None

    @staticmethod
    def _abrir_uri(uri):
        """
        Tenta abrir URI do Spotify pelo aplicativo do Windows.

        os.system("start ...") quase sempre retorna sem informar corretamente
        se o protocolo realmente foi aberto. os.startfile permite detectar uma
        falha real no Windows.
        """
        try:
            if os.name == "nt" and hasattr(os, "startfile"):
                os.startfile(uri)
                return True
        except OSError as erro:
            print(
                f"Não consegui abrir URI do Spotify ({uri}):",
                erro,
            )

        return False

    def _abrir_spotify(self):
        if self._abrir_uri("spotify:"):
            return True

        try:
            return bool(
                webbrowser.open(
                    "https://open.spotify.com"
                )
            )
        except Exception as erro:
            print(
                "Não consegui abrir Spotify Web:",
                erro,
            )
            return False

    def _fallback_busca(self, query):
        query = str(query or "").strip()

        if not query:
            self._abrir_spotify()
            return "Não consegui controlar o Spotify."

        print(
            f"Fallback Spotify: abrindo busca por {query}"
        )

        busca_uri = (
            "spotify:search:"
            + quote_plus(query)
        )

        if not self._abrir_uri(busca_uri):
            try:
                webbrowser.open(
                    "https://open.spotify.com/search/"
                    + quote_plus(query)
                )
            except Exception as erro:
                print(
                    "Erro ao abrir busca do Spotify:",
                    erro,
                )

        return "Não consegui tocar."

    @staticmethod
    def _status_erro(erro):
        status = getattr(
            erro,
            "http_status",
            None,
        )

        try:
            return int(status) if status is not None else None
        except (TypeError, ValueError):
            return None

    def _tratar_erro_spotify(
        self,
        erro,
        query=None,
    ):
        texto = str(erro)
        texto_upper = texto.upper()
        status = self._status_erro(
            erro
        )

        print(
            "Erro Spotify:",
            texto,
        )

        if (
            status == 403
            or "PREMIUM_REQUIRED" in texto_upper
            or "PREMIUM REQUIRED" in texto_upper
        ):
            if query:
                self._fallback_busca(
                    query
                )

            return (
                "O Spotify não permitiu esse controle. "
                "Esse recurso pode exigir Spotify Premium."
            )

        if status == 401:
            return (
                "A autorização do Spotify expirou ou ficou inválida. "
                "Preciso autenticar novamente."
            )

        if status == 429:
            return (
                "O Spotify limitou os comandos por alguns instantes. "
                "Tente novamente daqui a pouco."
            )

        if (
            "NO ACTIVE DEVICE" in texto_upper
            or "NO ACTIVE DEVICE FOUND" in texto_upper
        ):
            self._abrir_spotify()
            return "Preciso do Spotify aberto em um dispositivo."

        if status is not None and status >= 500:
            return (
                "O Spotify está indisponível no momento."
            )

        if query:
            return self._fallback_busca(
                query
            )

        return (
            "Não consegui controlar o Spotify agora."
        )

    # =========================================================
    # DISPOSITIVOS
    # =========================================================

    def listar_dispositivos_spotify(self):
        if not self.spotify_configurado():
            return []

        try:
            resposta = self.sp.devices()

            if not isinstance(
                resposta,
                dict,
            ):
                return []

            dispositivos = resposta.get(
                "devices",
                [],
            )

            return (
                dispositivos
                if isinstance(dispositivos, list)
                else []
            )

        except Exception as erro:
            print(
                "Erro ao listar dispositivos Spotify:",
                erro,
            )
            return []

    @staticmethod
    def _dispositivo_valido(dispositivo):
        return (
            isinstance(dispositivo, dict)
            and bool(dispositivo.get("id"))
            and not dispositivo.get(
                "is_restricted",
                False,
            )
        )

    def ativar_dispositivo_se_possivel(self):
        """
        Retorna um device_id utilizável.

        Se nenhum dispositivo estiver ativo, tenta transferir a reprodução
        para o primeiro dispositivo disponível. Isso evita depender de um ID
        inativo sem realmente ativá-lo.
        """
        dispositivos = [
            dispositivo
            for dispositivo
            in self.listar_dispositivos_spotify()
            if self._dispositivo_valido(
                dispositivo
            )
        ]

        if not dispositivos:
            return None

        ativo = next(
            (
                dispositivo
                for dispositivo in dispositivos
                if dispositivo.get(
                    "is_active"
                )
            ),
            None,
        )

        if ativo:
            return ativo.get(
                "id"
            )

        escolhido = dispositivos[0]
        device_id = escolhido.get(
            "id"
        )

        try:
            self.sp.transfer_playback(
                device_id,
                force_play=False,
            )

            print(
                "Spotify: reprodução transferida para "
                f"{escolhido.get('name', device_id)}"
            )

        except Exception as erro:
            # Alguns clientes/dispositivos aceitam start_playback com um
            # device_id ainda inativo; por isso mantemos o ID como fallback.
            print(
                "Spotify: não consegui ativar o dispositivo "
                f"{escolhido.get('name', device_id)}:",
                erro,
            )

        return device_id

    def _obter_dispositivo_com_fallback(self):
        dispositivo = (
            self.ativar_dispositivo_se_possivel()
        )

        if dispositivo:
            return dispositivo

        # Abrir o app pode fazer o dispositivo aparecer na API. Fazemos uma
        # única tentativa curta; não queremos adicionar vários segundos de
        # latência a todo comando.
        self._abrir_spotify()
        time.sleep(0.8)

        return (
            self.ativar_dispositivo_se_possivel()
        )

    # =========================================================
    # BUSCA
    # =========================================================

    @staticmethod
    def _normalizar_nome(texto):
        texto = str(
            texto or ""
        ).strip().lower()

        texto = unicodedata.normalize(
            "NFKD",
            texto,
        )

        texto = "".join(
            caractere
            for caractere in texto
            if not unicodedata.combining(
                caractere
            )
        )

        return re.sub(
            r"[^a-z0-9]",
            "",
            texto,
        )

    def buscar_musica(self, query):
        query = str(query or "").strip()

        if not query:
            return None

        print(
            f"Busca Spotify: {query}"
        )

        if not self.spotify_configurado():
            return None

        try:
            resultados = self.sp.search(
                q=query,
                type="track",
                limit=5,
                market="BR",
            )

            itens = (
                resultados.get(
                    "tracks",
                    {},
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    resultados,
                    dict,
                )
                else []
            )

            return (
                itens[0]
                if itens
                else None
            )

        except Exception as erro:
            print(
                "Erro ao buscar música:",
                erro,
            )
            return None

    # =========================================================
    # REPRODUÇÃO
    # =========================================================

    def tocar_musica(self, query):
        query = str(query or "").strip()

        if not query:
            return (
                "Qual música você quer que eu toque?"
            )

        if not self.spotify_configurado():
            return self._fallback_busca(
                query
            )

        print(
            f"Busca Spotify: {query}"
        )

        try:
            resultados = self.sp.search(
                q=query,
                type="track",
                limit=10,
                market="BR",
            )

            faixas = (
                resultados.get(
                    "tracks",
                    {},
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    resultados,
                    dict,
                )
                else []
            )

            if not faixas:
                print(
                    "Spotify: nenhuma faixa encontrada "
                    f"para {query}"
                )
                return (
                    "Não encontrei essa música."
                )

            primeira_faixa = faixas[0]

            nome = primeira_faixa.get(
                "name",
                "essa música",
            )

            artistas = ", ".join(
                artista.get(
                    "name",
                    ""
                )
                for artista
                in primeira_faixa.get(
                    "artists",
                    [],
                )
                if isinstance(
                    artista,
                    dict,
                )
            ).strip(", ")

            uri = primeira_faixa.get(
                "uri"
            )

            print(
                f"Spotify encontrou: {nome} - {artistas}"
            )
            print(
                f"Spotify URI principal: {uri}"
            )

            uris = [
                faixa.get(
                    "uri"
                )
                for faixa in faixas
                if isinstance(
                    faixa,
                    dict,
                )
                and faixa.get(
                    "uri"
                )
            ]

            if not uris:
                return (
                    "Não encontrei músicas válidas para tocar."
                )

            dispositivo = (
                self._obter_dispositivo_com_fallback()
            )

            if not dispositivo:
                print(
                    "Spotify: nenhum dispositivo disponível."
                )
                return (
                    "Preciso do Spotify aberto."
                )

            print(
                f"Spotify dispositivo: {dispositivo}"
            )
            print(
                f"Fila Spotify criada com {len(uris)} músicas."
            )

            self.sp.start_playback(
                device_id=dispositivo,
                uris=uris,
            )

            return "Ok."

        except SpotifyException as erro:
            return self._tratar_erro_spotify(
                erro,
                query,
            )

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro,
                query,
            )

    def tocar_artista(self, query):
        query_original = str(
            query or ""
        ).strip()

        if not query_original:
            return (
                "Qual artista você quer ouvir?"
            )

        if not self.spotify_configurado():
            return self._fallback_busca(
                query_original
            )

        try:
            query_normalizada = (
                self._normalizar_nome(
                    query_original
                )
            )

            print(
                "Busca Spotify por artista: "
                f"{query_original}"
            )

            resultados = self.sp.search(
                q=f'artist:"{query_original}"',
                type="artist",
                limit=10,
                market="BR",
            )

            itens = (
                resultados.get(
                    "artists",
                    {},
                ).get(
                    "items",
                    [],
                )
                if isinstance(
                    resultados,
                    dict,
                )
                else []
            )

            if not itens:
                resultados = self.sp.search(
                    q=query_original,
                    type="artist",
                    limit=10,
                    market="BR",
                )

                itens = (
                    resultados.get(
                        "artists",
                        {},
                    ).get(
                        "items",
                        [],
                    )
                    if isinstance(
                        resultados,
                        dict,
                    )
                    else []
                )

            if not itens:
                print(
                    "Spotify: nenhum artista encontrado "
                    f"para {query_original}"
                )
                return (
                    "Não encontrei esse artista."
                )

            print(
                "Candidatos encontrados:"
            )

            for candidato in itens[:10]:
                if isinstance(
                    candidato,
                    dict,
                ):
                    print(
                        " -",
                        candidato.get(
                            "name",
                            "desconhecido",
                        ),
                    )

            artista_exato = None

            for candidato in itens:
                if not isinstance(
                    candidato,
                    dict,
                ):
                    continue

                nome_candidato = candidato.get(
                    "name",
                    "",
                )

                if (
                    self._normalizar_nome(
                        nome_candidato
                    )
                    == query_normalizada
                ):
                    artista_exato = candidato
                    break

            artista = artista_exato

            if artista is None:
                melhor_artista = None
                melhor_score = 0.0

                for candidato in itens:
                    if not isinstance(
                        candidato,
                        dict,
                    ):
                        continue

                    nome_candidato = candidato.get(
                        "name",
                        "",
                    )

                    nome_normalizado = (
                        self._normalizar_nome(
                            nome_candidato
                        )
                    )

                    score = SequenceMatcher(
                        None,
                        query_normalizada,
                        nome_normalizado,
                    ).ratio()

                    print(
                        "Similaridade: "
                        f"{query_original} <-> "
                        f"{nome_candidato}: "
                        f"{score:.3f}"
                    )

                    if score > melhor_score:
                        melhor_score = score
                        melhor_artista = candidato

                if (
                    melhor_artista is None
                    or melhor_score < 0.65
                ):
                    print(
                        "Spotify não encontrou artista "
                        "com confiança suficiente."
                    )
                    return (
                        f"Não encontrei o artista "
                        f"{query_original} com segurança."
                    )

                artista = melhor_artista

            nome_artista = artista.get(
                "name",
                query_original,
            )
            uri_artista = artista.get(
                "uri"
            )

            print(
                f"Spotify artista escolhido: {nome_artista}"
            )
            print(
                f"Spotify URI: {uri_artista}"
            )

            if not uri_artista:
                return (
                    "Não encontrei esse artista."
                )

            dispositivo = (
                self._obter_dispositivo_com_fallback()
            )

            if not dispositivo:
                print(
                    "Spotify: nenhum dispositivo disponível."
                )
                return (
                    "Preciso do Spotify aberto."
                )

            print(
                f"Spotify dispositivo: {dispositivo}"
            )

            self.sp.start_playback(
                device_id=dispositivo,
                context_uri=uri_artista,
            )

            return "Ok."

        except SpotifyException as erro:
            return self._tratar_erro_spotify(
                erro,
                query_original,
            )

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro,
                query_original,
            )

    # =========================================================
    # CONTROLES
    # =========================================================

    def pausar_spotify(self):
        if not self.spotify_configurado():
            return (
                "Preciso configurar o Spotify primeiro "
                "para pausar pela API."
            )

        try:
            dispositivo = (
                self.ativar_dispositivo_se_possivel()
            )

            self.sp.pause_playback(
                device_id=dispositivo
                if dispositivo
                else None
            )

            return "Pausado."

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro
            )

    def continuar_spotify(self):
        if not self.spotify_configurado():
            self._abrir_spotify()

            return (
                "Abri o Spotify. Para continuar direto "
                "pela API, preciso da configuração completa."
            )

        try:
            dispositivo = (
                self._obter_dispositivo_com_fallback()
            )

            if not dispositivo:
                return (
                    "Preciso do Spotify aberto."
                )

            self.sp.start_playback(
                device_id=dispositivo
            )

            return "Continuando."

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro
            )

    def proxima_musica(self):
        if not self.spotify_configurado():
            return (
                "Preciso configurar o Spotify primeiro "
                "para avançar pela API."
            )

        try:
            dispositivo = (
                self.ativar_dispositivo_se_possivel()
            )

            self.sp.next_track(
                device_id=dispositivo
                if dispositivo
                else None
            )

            return "Próxima."

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro
            )

    def musica_anterior(self):
        if not self.spotify_configurado():
            return (
                "Preciso configurar o Spotify primeiro "
                "para voltar pela API."
            )

        try:
            dispositivo = (
                self.ativar_dispositivo_se_possivel()
            )

            self.sp.previous_track(
                device_id=dispositivo
                if dispositivo
                else None
            )

            return "Voltando."

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro
            )

    def volume_spotify(
        self,
        percentual,
    ):
        if not self.spotify_configurado():
            return (
                "Preciso configurar o Spotify primeiro "
                "para controlar o volume pela API."
            )

        try:
            percentual = max(
                0,
                min(
                    100,
                    int(percentual),
                ),
            )

            dispositivo = (
                self.ativar_dispositivo_se_possivel()
            )

            self.sp.volume(
                percentual,
                device_id=dispositivo
                if dispositivo
                else None,
            )

            return "Ok."

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro
            )

    # =========================================================
    # ESTADO
    # =========================================================

    def estado_spotify(self):
        if not self.spotify_configurado():
            return (
                "Spotify API ainda não está configurada."
            )

        try:
            atual = (
                self.sp.current_user_playing_track()
            )

            if (
                not atual
                or not isinstance(
                    atual,
                    dict,
                )
                or not atual.get(
                    "item"
                )
            ):
                return (
                    "Não encontrei música tocando agora."
                )

            item = atual[
                "item"
            ]

            if not isinstance(
                item,
                dict,
            ):
                return (
                    "Não encontrei música tocando agora."
                )

            nome = item.get(
                "name",
                "música desconhecida",
            )

            artistas = ", ".join(
                artista.get(
                    "name",
                    ""
                )
                for artista
                in item.get(
                    "artists",
                    [],
                )
                if isinstance(
                    artista,
                    dict,
                )
            ).strip(", ")

            print(
                f"Spotify tocando agora: {nome} - {artistas}"
            )

            if artistas:
                return (
                    f"Tocando agora: {nome}, de {artistas}."
                )

            return (
                f"Tocando agora: {nome}."
            )

        except Exception as erro:
            return self._tratar_erro_spotify(
                erro
            )