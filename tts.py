import asyncio
import os
import re
import tempfile
import threading
import time
from pathlib import Path

import edge_tts
from playsound import playsound


class OrionSpeaker:
    def __init__(
        self,
        voice="pt-BR-DonatoNeural",
        rate="+2%",
        pitch="-2Hz",
        volume="+0%",
    ):
        """
        TTS do Orion.

        Mantém a mesma interface usada pelo main.py, mas deixa a fala mais
        natural e robusta.

        A voz padrão foi trocada do Antonio para Donato. Caso a voz escolhida
        não esteja disponível no Edge TTS, o Orion tenta automaticamente
        outras vozes pt-BR antes de desistir.
        """
        self.voice = voice
        self.rate = rate
        self.pitch = pitch
        self.volume = volume

        self._falando = False
        self._lock = threading.Lock()
        self._speak_lock = threading.Lock()

        self._fallback_voices = (
            "pt-BR-DonatoNeural",
            "pt-BR-FabioNeural",
            "pt-BR-HumbertoNeural",
            "pt-BR-JulioNeural",
            "pt-BR-AntonioNeural",
        )

    def esta_falando(self):
        with self._lock:
            return self._falando

    def _set_falando(self, valor):
        with self._lock:
            self._falando = bool(valor)

    @staticmethod
    def _limpar_texto_para_fala(texto):
        """
        Remove formatação que fica estranha quando lida em voz alta,
        sem alterar o conteúdo da resposta.
        """
        texto = str(texto or "").strip()

        if not texto:
            return ""

        # Markdown simples.
        texto = re.sub(r"`{1,3}", "", texto)
        texto = re.sub(r"\*\*(.*?)\*\*", r"\1", texto)
        texto = re.sub(r"__(.*?)__", r"\1", texto)
        texto = re.sub(r"(?m)^\s*[-*•]\s+", "", texto)

        # Espaços e quebras excessivas.
        texto = re.sub(r"\s+", " ", texto)

        return texto.strip()

    @staticmethod
    def _novo_arquivo_temporario():
        """
        Gera um nome realmente único para evitar colisão entre duas respostas
        criadas no mesmo milissegundo.
        """
        handle = tempfile.NamedTemporaryFile(
            prefix="orion_resposta_",
            suffix=".mp3",
            delete=False,
        )

        caminho = Path(handle.name)
        handle.close()

        # O Edge TTS deve criar/escrever o arquivo.
        try:
            caminho.unlink()
        except OSError:
            pass

        return caminho

    def _vozes_para_tentar(self):
        """
        Prioriza a voz configurada pelo usuário e depois usa fallbacks.
        """
        vozes = [self.voice]

        for voice in self._fallback_voices:
            if voice not in vozes:
                vozes.append(voice)

        return vozes

    async def _gerar_voz(self, texto):
        texto = self._limpar_texto_para_fala(
            texto
        )

        if not texto:
            return None

        ultimo_erro = None

        for voice in self._vozes_para_tentar():
            arquivo = self._novo_arquivo_temporario()

            try:
                communicate = edge_tts.Communicate(
                    texto,
                    voice=voice,
                    rate=self.rate,
                    pitch=self.pitch,
                    volume=self.volume,
                )

                await communicate.save(
                    str(arquivo)
                )

                if (
                    arquivo.exists()
                    and arquivo.stat().st_size > 0
                ):
                    if voice != self.voice:
                        print(
                            f"TTS: voz {self.voice} indisponível; "
                            f"usando {voice}."
                        )

                    return str(arquivo)

            except Exception as erro:
                ultimo_erro = erro

            finally:
                # Se a tentativa falhou, não deixe MP3 vazio no temp.
                if (
                    arquivo.exists()
                    and arquivo.stat().st_size == 0
                ):
                    try:
                        arquivo.unlink()
                    except OSError:
                        pass

        if ultimo_erro is not None:
            raise ultimo_erro

        raise RuntimeError(
            "Nenhuma voz TTS conseguiu gerar áudio."
        )

    def _tocar_audio(self, arquivo):
        try:
            if not arquivo:
                return

            playsound(
                str(arquivo)
            )

        except Exception as erro:
            print(
                "Erro ao tocar áudio:",
                erro,
            )

        finally:
            if arquivo:
                try:
                    Path(arquivo).unlink(
                        missing_ok=True
                    )
                except OSError:
                    pass

            # Pequena margem para não religar o microfone exatamente no final
            # do áudio e capturar o eco da própria resposta.
            time.sleep(0.15)

            self._set_falando(
                False
            )

            try:
                self._speak_lock.release()
            except RuntimeError:
                pass

    def falar(self, texto):
        texto = self._limpar_texto_para_fala(
            texto
        )

        if not texto:
            return

        print(
            f"Orion: {texto}"
        )

        # Evita duas respostas tocando por cima uma da outra.
        if not self._speak_lock.acquire(
            blocking=False
        ):
            print(
                "TTS: já existe uma resposta sendo reproduzida."
            )
            return

        self._set_falando(
            True
        )

        arquivo = None

        try:
            arquivo = asyncio.run(
                self._gerar_voz(
                    texto
                )
            )

            if not arquivo:
                raise RuntimeError(
                    "TTS não gerou arquivo de áudio."
                )

            thread = threading.Thread(
                target=self._tocar_audio,
                args=(arquivo,),
                daemon=True,
                name="OrionTTSPlayback",
            )

            thread.start()

        except Exception as erro:
            print(
                "Erro ao falar:",
                erro,
            )

            if arquivo:
                try:
                    Path(arquivo).unlink(
                        missing_ok=True
                    )
                except OSError:
                    pass

            self._set_falando(
                False
            )

            try:
                self._speak_lock.release()
            except RuntimeError:
                pass