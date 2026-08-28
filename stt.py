import re
import time

import numpy as np
from faster_whisper import WhisperModel

from config import MODELO_WHISPER, WHISPER_INITIAL_PROMPT


class WhisperTranscriber:
    def __init__(self, modelo=None):
        """
        Transcritor de voz do Orion.

        `modelo` existe apenas para permitir testes isolados. No uso normal,
        o Orion continua criando WhisperTranscriber() sem argumentos.
        """
        if modelo is not None:
            self.model = modelo
            return

        print(
            f"Carregando Whisper {MODELO_WHISPER} "
            "em GPU/CUDA int8_float16..."
        )

        self.model = WhisperModel(
            MODELO_WHISPER,
            device="cuda",
            compute_type="int8_float16",
        )

    @staticmethod
    def normalizar_audio(audio):
        """
        Prepara o áudio para o Whisper sem amplificar ruído quase silencioso.

        O código antigo sempre levava o maior pico para 0.9. Em um trecho
        muito baixo, isso podia transformar ruído de fundo em sinal forte.
        Agora o ganho é limitado e valores inválidos são removidos.
        """
        if audio is None:
            return np.array([], dtype=np.float32)

        audio = np.asarray(
            audio,
            dtype=np.float32,
        ).reshape(-1)

        if audio.size == 0:
            return audio

        # Evita NaN/Inf chegando ao Whisper.
        audio = np.nan_to_num(
            audio,
            nan=0.0,
            posinf=0.0,
            neginf=0.0,
        )

        # Remove pequeno offset DC do microfone.
        media = float(np.mean(audio))
        if abs(media) > 1e-6:
            audio = audio - media

        pico = float(
            np.max(
                np.abs(audio)
            )
        )

        if pico <= 1e-6:
            return audio

        # Não amplifica agressivamente gravações quase silenciosas.
        # O máximo de 4x ainda ajuda fala baixa sem transformar qualquer
        # ruído residual em um áudio artificialmente alto.
        ganho = min(
            0.9 / pico,
            4.0,
        )

        if ganho > 1.0:
            audio = audio * ganho

        # Garante a faixa esperada pelo Whisper.
        return np.clip(
            audio,
            -1.0,
            1.0,
        ).astype(
            np.float32,
            copy=False,
        )

    @staticmethod
    def _limpar_texto(texto):
        """
        Faz somente limpeza estrutural.

        Não tenta adivinhar ou corrigir comandos. Essa responsabilidade fica
        com intent_router.py / ai_router.py para evitar o STT inventar sentido.
        """
        texto = str(
            texto or ""
        ).strip().lower()

        texto = re.sub(
            r"\s+",
            " ",
            texto,
        )

        wake_words = (
            "hey jarvis",
            "hey, jarvis",
            "ei jarvis",
            "ei, jarvis",
            "hey travis",
            "hey, travis",
        )

        for wake_word in wake_words:
            if texto.startswith(
                wake_word
            ):
                texto = texto[
                    len(wake_word):
                ].strip(
                    " ,.!?-"
                )
                break

        return texto.strip()

    def transcrever_audio(self, audio):
        audio = self.normalizar_audio(
            audio
        )

        if audio.size == 0:
            return ""

        # Um áudio praticamente silencioso não precisa ocupar a GPU.
        rms = float(
            np.sqrt(
                np.mean(
                    np.square(audio)
                )
            )
        )

        if rms < 1e-5:
            return ""

        inicio = time.perf_counter()

        segments, _ = self.model.transcribe(
            audio,
            language="pt",
            task="transcribe",
            vad_filter=True,
            vad_parameters={
                # Mantém pausas curtas dentro de comandos rápidos.
                "min_silence_duration_ms": 250,
            },
            # Beam 1 era rápido, mas muito agressivo. Beam 3 melhora a chance
            # de recuperar frases curtas sem voltar ao custo alto do padrão 5.
            beam_size=3,
            temperature=0.0,
            condition_on_previous_text=False,
            initial_prompt=WHISPER_INITIAL_PROMPT,
        )

        partes = []

        for segment in segments:
            trecho = str(
                getattr(
                    segment,
                    "text",
                    "",
                )
            ).strip()

            if trecho:
                partes.append(
                    trecho
                )

        tempo = (
            time.perf_counter()
            - inicio
        )

        texto = self._limpar_texto(
            " ".join(partes)
        )

        print(
            f"Whisper levou {tempo:.3f}s"
        )

        return texto