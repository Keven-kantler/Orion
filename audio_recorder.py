import re
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


# A pausa curta continua sendo usada apenas como primeiro candidato a fim de fala.
# Quando a transcrição provisória termina de forma claramente incompleta, o
# Orion concede uma pequena janela extra para o usuário continuar pensando.
TEMPO_EXTRA_FRASE_INCOMPLETA = 3.0

# O antigo limite de 6 s continua servindo para encerrar a escuta quando
# ninguém começou a falar. Depois que a fala começou, este limite de segurança
# evita uma gravação infinita sem cortar comandos normais mais longos.
LIMITE_SEGURANCA_FALA_SEGUNDOS = 30.0


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

    @staticmethod
    def _texto_parece_incompleto(texto):
        """
        Detecta apenas sinais fortes de que a pessoa ainda não terminou.

        A regra é propositalmente conservadora: se houver dúvida, tratamos a
        frase como completa para não deixar o Orion lento. O objetivo principal
        é proteger pausas naturais em construções claramente abertas, como
        "qual a diferença entre Java e...".
        """
        texto_original = str(texto or "").strip().lower()

        if not texto_original:
            return True

        # Interrogação/exclamação explícita é um sinal forte de turno completo.
        # Reticências têm o sentido oposto e indicam continuação provável.
        if texto_original.endswith(("...", "…")):
            return True

        if texto_original.endswith(("?", "!")):
            return False

        texto = re.sub(r"[.!?…]+$", "", texto_original).strip()

        if not texto:
            return True

        finais_abertos = (
            " e",
            " ou",
            " mas",
            " porque",
            " por que",
            " entre",
            " com",
            " para",
            " de",
            " do",
            " da",
            " dos",
            " das",
            " em",
            " no",
            " na",
            " nos",
            " nas",
            " que",
            " se",
            " quando",
            " como",
            " qual",
            " quais",
        )

        texto_com_espaco = f" {texto}"

        if any(texto_com_espaco.endswith(final) for final in finais_abertos):
            return True

        return False

    def gravar_ate_silencio(
        self,
        deve_bloquear=None,
        transcrever_parcial=None,
    ):
        """
        Grava até o fim natural do turno de fala.

        Fluxo:
        1. O áudio detecta uma primeira pausa curta.
        2. Se houver um transcritor disponível, fazemos uma transcrição
           provisória.
        3. Frase completa -> encerra imediatamente.
        4. Frase claramente incompleta -> concede uma janela extra para a
           pessoa continuar.

        Retorna uma tupla ``(audio, texto_pretranscrito)``. O texto provisório
        é reaproveitado pelo main quando já representa o áudio final, evitando
        uma segunda transcrição desnecessária.
        """
        print("Ouvindo comando...")

        blocos = []
        inicio = time.time()
        inicio_fala = None
        tempo_silencio = 0.0
        fala_detectada = False
        volumes_iniciais = []
        limite_dinamico = SILENCIO_LIMIAR_AUDIO
        ruido_ambiente = SILENCIO_LIMIAR_AUDIO

        texto_pretranscrito = None
        texto_incompleto = False
        silencio_verificado = False

        while True:
            if deve_bloquear and deve_bloquear():
                print("Gravação cancelada porque o Orion está falando.")
                return np.array([], dtype=np.float32), None

            bloco = self.gravar_bloco()
            blocos.append(bloco)

            volume = self._volume_bloco(bloco)
            duracao_total = time.time() - inicio

            if duracao_total <= 1.0 and not fala_detectada:
                volumes_iniciais.append(volume)

                if volumes_iniciais:
                    ruido_ambiente = float(np.median(volumes_iniciais))
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
                if not fala_detectada:
                    inicio_fala = time.time()

                fala_detectada = True
                tempo_silencio = 0.0
                texto_incompleto = False
                silencio_verificado = False
                texto_pretranscrito = None
            else:
                tempo_silencio += TEMPO_BLOCO_AUDIO

            # Se ninguém começou a falar, preservamos o timeout atual da
            # sessão. Assim o Orion ainda volta para a wake word normalmente.
            if (
                not fala_detectada
                and duracao_total >= GRAVACAO_AUTO_MAX_SEGUNDOS
            ):
                print("Nenhuma fala detectada dentro do tempo de espera.")
                break

            if not fala_detectada:
                continue

            duracao_fala = (
                time.time() - inicio_fala
                if inicio_fala is not None
                else duracao_total
            )

            if duracao_fala >= LIMITE_SEGURANCA_FALA_SEGUNDOS:
                print("Limite de segurança da fala atingido.")
                break

            pode_avaliar_fim = (
                duracao_total >= GRAVACAO_AUTO_MIN_SEGUNDOS
                and tempo_silencio >= SILENCIO_SEGUNDOS_AUTO_STOP
            )

            if not pode_avaliar_fim:
                continue

            # Sem transcritor, preserva o comportamento antigo. Isso mantém
            # compatibilidade com qualquer uso isolado do gravador.
            if transcrever_parcial is None:
                print("Silêncio detectado. Encerrando gravação.")
                break

            if not silencio_verificado:
                audio_parcial = np.concatenate(blocos, axis=0).flatten()

                try:
                    texto_pretranscrito = transcrever_parcial(audio_parcial)
                except Exception as erro:
                    print(
                        "Falha na checagem de fim de fala; "
                        f"usando silêncio como fallback: {erro}"
                    )
                    texto_pretranscrito = None
                    print("Silêncio detectado. Encerrando gravação.")
                    break

                texto_incompleto = self._texto_parece_incompleto(
                    texto_pretranscrito
                )
                silencio_verificado = True

                if not texto_incompleto:
                    print("Fim de fala confirmado pelo conteúdo.")
                    break

                print(
                    "Pausa detectada, mas a frase parece incompleta. "
                    "Continuando a escuta..."
                )

            # Se a pessoa realmente parou numa frase incompleta, não deixamos
            # o microfone preso até o limite máximo. A janela extra só existe
            # porque o conteúdo indicou continuação provável.
            if (
                texto_incompleto
                and tempo_silencio
                >= SILENCIO_SEGUNDOS_AUTO_STOP
                + TEMPO_EXTRA_FRASE_INCOMPLETA
            ):
                print(
                    "A frase parecia incompleta, mas não houve continuação. "
                    "Encerrando gravação."
                )
                # O áudio final ganhou apenas silêncio; a transcrição já feita
                # continua válida e pode ser reaproveitada.
                break

        if not blocos or not fala_detectada:
            print("Nenhuma fala detectada.")
            return np.array([], dtype=np.float32), None

        audio_final = np.concatenate(blocos, axis=0).flatten()
        return audio_final, texto_pretranscrito

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
