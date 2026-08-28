import threading
import time

import numpy as np
import sounddevice as sd
from pynput.keyboard import Key, Listener

from config import (
    GRAVACAO_AUTO_MAX_SEGUNDOS,
    GRAVACAO_AUTO_MIN_SEGUNDOS,
    INTERVALO_DEBOUNCE_TECLA,
    SILENCIO_LIMIAR_AUDIO,
    SILENCIO_SEGUNDOS_AUTO_STOP,
    TAXA_AUDIO,
    TEMPO_BLOCO_AUDIO,
)


class ManualAudioRecorder:
    def __init__(self):
        self._toggle = threading.Event()
        self._ultimo_toque = 0
        self._listener = Listener(on_press=self._ao_pressionar_tecla)

    def iniciar_listener(self):
        self._listener.start()

    def parar_listener(self):
        self._listener.stop()

    def _ao_pressionar_tecla(self, tecla):
        if tecla != Key.down:
            return

        agora = time.time()

        if agora - self._ultimo_toque < INTERVALO_DEBOUNCE_TECLA:
            return

        self._ultimo_toque = agora
        self._toggle.set()

    def esperar_toggle(self):
        self._toggle.wait()
        self._toggle.clear()

    def gravar_bloco(self):
        audio = sd.rec(
            int(TAXA_AUDIO * TEMPO_BLOCO_AUDIO),
            samplerate=TAXA_AUDIO,
            channels=1,
            dtype="float32",
        )

        sd.wait()

        return audio

    def gravar_ate_toggle(self, deve_bloquear=None):
        print("Gravando...")
        print("Pressione seta para baixo novamente para parar")

        blocos = []
        self._toggle.clear()

        while True:
            if deve_bloquear and deve_bloquear():
                print("Gravação cancelada porque o Orion está falando.")
                self._toggle.clear()

                return np.array([], dtype=np.float32)

            bloco = self.gravar_bloco()
            blocos.append(bloco)

            if self._toggle.is_set():
                self._toggle.clear()
                print("Gravação encerrada.")

                break

        if not blocos:
            return np.array([], dtype=np.float32)

        return np.concatenate(blocos, axis=0).flatten()

    def gravar_ate_silencio(self, deve_bloquear=None):
        print("Ouvindo comando...")

        blocos = []

        inicio = time.time()

        tempo_silencio = 0.0
        fala_detectada = False

        # Guarda os volumes iniciais para estimar
        # automaticamente o ruído ambiente.
        volumes_iniciais = []

        # Começamos usando o valor mínimo definido no config.py.
        limite_dinamico = SILENCIO_LIMIAR_AUDIO

        ruido_ambiente = SILENCIO_LIMIAR_AUDIO

        while True:
            if deve_bloquear and deve_bloquear():
                print("Gravação cancelada porque o Orion está falando.")

                return np.array([], dtype=np.float32)

            bloco = self.gravar_bloco()
            blocos.append(bloco)

            volume = self._volume_bloco(bloco)

            duracao_total = time.time() - inicio

            # Durante aproximadamente o primeiro segundo,
            # usamos os volumes capturados para estimar
            # o nível de ruído ambiente.
            #
            # A mediana ajuda a evitar que um pico isolado
            # estrague a calibração.
            if duracao_total <= 1.0:
                volumes_iniciais.append(volume)

                if volumes_iniciais:
                    ruido_ambiente = float(
                        np.median(volumes_iniciais)
                    )

                    # O limite de fala fica um pouco acima
                    # do ruído ambiente.
                    #
                    # SILENCIO_LIMIAR_AUDIO continua sendo
                    # o valor mínimo permitido.
                    limite_dinamico = max(
                        SILENCIO_LIMIAR_AUDIO,
                        ruido_ambiente * 1.35,
                    )

            print(
                f"Volume comando: {volume:.4f} | "
                f"Ruído: {ruido_ambiente:.4f} | "
                f"Limite: {limite_dinamico:.4f}"
            )

            if volume >= limite_dinamico:
                fala_detectada = True
                tempo_silencio = 0.0

            else:
                tempo_silencio += TEMPO_BLOCO_AUDIO

            pode_parar_por_silencio = (
                fala_detectada
                and duracao_total >= GRAVACAO_AUTO_MIN_SEGUNDOS
                and tempo_silencio >= SILENCIO_SEGUNDOS_AUTO_STOP
            )

            if pode_parar_por_silencio:
                print("Silêncio detectado. Encerrando gravação.")

                break

            if duracao_total >= GRAVACAO_AUTO_MAX_SEGUNDOS:
                print("Tempo máximo de gravação atingido.")

                break

        if not blocos or not fala_detectada:
            print("Nenhuma fala detectada.")

            return np.array([], dtype=np.float32)

        return np.concatenate(blocos, axis=0).flatten()

    def _volume_bloco(self, bloco):
        if bloco.size == 0:
            return 0.0

        bloco_float = bloco.astype(np.float32).reshape(-1)

        return float(
            np.sqrt(
                np.mean(
                    bloco_float ** 2
                )
            )
        )