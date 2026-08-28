import time
import traceback
from pathlib import Path

import numpy as np
import sounddevice as sd

from config import (
    AUDIO_INPUT_DEVICE,
    OPENWAKEWORD_BLOCK_SAMPLES,
    OPENWAKEWORD_MODEL,
    OPENWAKEWORD_THRESHOLD,
    TAXA_AUDIO,
    WAKEWORD_COOLDOWN_SEGUNDOS,
)


def _modelos_disponiveis():
    try:
        import openwakeword

        return sorted(
            openwakeword.MODELS.keys()
        )
    except Exception:
        return []


def _resolver_modelo_configurado():
    """
    Aceita tanto um modelo embutido do OpenWakeWord, como "hey_jarvis",
    quanto o caminho para um modelo customizado .onnx/.tflite.

    Isso deixa o Orion preparado para trocar a wake word no futuro sem
    precisar alterar novamente este arquivo.
    """
    modelo_configurado = str(
        OPENWAKEWORD_MODEL or ""
    ).strip()

    if not modelo_configurado:
        return "hey_jarvis", False

    caminho = Path(
        modelo_configurado
    ).expanduser()

    if caminho.is_file():
        return str(
            caminho.resolve()
        ), True

    return modelo_configurado, False


def carregar_openwakeword():
    print(
        "Carregando OpenWakeWord..."
    )

    modelo, modelo_customizado = (
        _resolver_modelo_configurado()
    )

    print(
        "Config OpenWakeWord: "
        f"modelo={modelo}, "
        f"threshold={OPENWAKEWORD_THRESHOLD}"
    )

    try:
        import openwakeword
        from openwakeword.model import Model
        from openwakeword.utils import download_models

    except ImportError as erro:
        print(
            "OpenWakeWord não está instalado:",
            erro,
        )
        return None

    disponiveis = _modelos_disponiveis()

    if not modelo_customizado:
        if disponiveis and modelo not in disponiveis:
            print(
                f"Modelo OpenWakeWord '{modelo}' "
                "não encontrado."
            )
            print(
                "Modelos disponíveis:",
                ", ".join(
                    disponiveis
                ),
            )

            modelo = (
                "hey_jarvis"
                if "hey_jarvis" in disponiveis
                else disponiveis[0]
            )

            print(
                f"Usando modelo padrão: {modelo}"
            )

        # Baixa/verifica somente o modelo realmente usado.
        # Segundo a própria biblioteca, os arquivos ficam em cache depois.
        try:
            download_models(
                models=[modelo]
            )
        except TypeError:
            # Compatibilidade com versões antigas do OpenWakeWord.
            try:
                download_models()
            except Exception as erro:
                print(
                    "Aviso: não consegui baixar/verificar "
                    "modelos do OpenWakeWord:",
                    erro,
                )
        except Exception as erro:
            print(
                "Aviso: não consegui baixar/verificar "
                "o modelo do OpenWakeWord:",
                erro,
            )

    try:
        wake_model = Model(
            wakeword_models=[modelo],
            inference_framework="onnx",
        )

        modelos_ativos = list(
            wake_model.models.keys()
        )

        print(
            f"OpenWakeWord carregado com modelo: {modelo}"
        )

        print(
            "Modelos ativos:",
            ", ".join(
                modelos_ativos
            ),
        )

        return wake_model

    except Exception as erro:
        print(
            "Falha ao carregar OpenWakeWord:",
            erro,
        )
        print(
            "Voltando para modo manual."
        )
        return None


def _resolver_dispositivo_audio():
    print(
        "Dispositivos de áudio disponíveis:"
    )

    try:
        dispositivos = sd.query_devices()
        print(
            dispositivos
        )
    except Exception as erro:
        print(
            "Não consegui listar dispositivos de áudio:",
            erro,
        )
        dispositivos = []

    configurado = str(
        AUDIO_INPUT_DEVICE or ""
    ).strip()

    if not configurado:
        try:
            padrao = sd.query_devices(
                kind="input"
            )

            print(
                "Microfone usado: padrão do sistema - "
                f"{padrao.get('name', 'desconhecido')}"
            )

        except Exception:
            print(
                "Microfone usado: padrão do sistema"
            )

        return None

    # Primeiro tenta índice numérico.
    try:
        indice = int(
            configurado
        )

        nome = "desconhecido"

        try:
            nome = sd.query_devices(
                indice
            ).get(
                "name",
                "desconhecido",
            )
        except Exception:
            pass

        print(
            f"Microfone usado: índice {indice} - {nome}"
        )

        return indice

    except ValueError:
        pass

    # Também permite configurar pelo nome, por exemplo:
    # AUDIO_INPUT_DEVICE=H510-PRO Wireless
    configurado_lower = (
        configurado.lower()
    )

    try:
        for indice, dispositivo in enumerate(
            dispositivos
        ):
            nome = str(
                dispositivo.get(
                    "name",
                    "",
                )
            )

            canais_entrada = int(
                dispositivo.get(
                    "max_input_channels",
                    0,
                )
            )

            if (
                canais_entrada > 0
                and configurado_lower
                in nome.lower()
            ):
                print(
                    "Microfone usado: "
                    f"índice {indice} - {nome}"
                )

                return indice

    except Exception:
        pass

    print(
        "AUDIO_INPUT_DEVICE não encontrado: "
        f"{configurado}. "
        "Usando padrão do sistema."
    )

    return None


def _volume_aproximado(
    audio_int16,
):
    if (
        audio_int16 is None
        or audio_int16.size == 0
    ):
        return 0.0

    audio_float = (
        audio_int16.astype(
            np.float32
        )
        / 32768.0
    )

    return float(
        np.sqrt(
            np.mean(
                audio_float ** 2
            )
        )
    )


def _formatar_scores(
    predicoes,
):
    partes = []

    for nome, score in predicoes.items():
        try:
            score_float = float(
                score
            )
        except (TypeError, ValueError):
            score_float = 0.0

        partes.append(
            f"{nome}={score_float:.3f}"
        )

    return " | ".join(
        partes
    )


def _resetar_modelo(
    wake_model,
):
    """
    Limpa o histórico interno do OpenWakeWord.

    Isso é importante depois de o Orion falar ou depois de uma ativação:
    o modelo mantém buffers internos de áudio e não queremos que trechos
    antigos influenciem uma nova detecção.
    """
    try:
        wake_model.reset()
    except Exception:
        pass


def detectar_loop_openwakeword(
    wake_model,
    callback_processar_audio,
    deve_ignorar=None,
):
    print(
        "Orion aguardando wake word..."
    )
    print(
        "Aguardando wake word..."
    )

    dispositivo = (
        _resolver_dispositivo_audio()
    )

    modelo_ativo = next(
        iter(
            wake_model.models.keys()
        ),
        str(
            OPENWAKEWORD_MODEL
        ),
    )

    ultimo_log = 0.0
    ultima_deteccao = 0.0
    estava_ignorando = False

    try:
        with sd.InputStream(
            samplerate=TAXA_AUDIO,
            blocksize=OPENWAKEWORD_BLOCK_SAMPLES,
            device=dispositivo,
            channels=1,
            dtype="int16",
        ) as stream:
            print(
                "Formato enviado ao OpenWakeWord: "
                f"samplerate={TAXA_AUDIO}, "
                "channels=1, dtype=int16, "
                f"blocksize={OPENWAKEWORD_BLOCK_SAMPLES} samples"
            )

            print(
                f"Threshold ativo: {OPENWAKEWORD_THRESHOLD}"
            )

            while True:
                # Sempre lê o stream. O código antigo dormia enquanto o Orion
                # falava e podia deixar áudio acumulado no buffer.
                audio, overflow = stream.read(
                    OPENWAKEWORD_BLOCK_SAMPLES
                )

                if overflow:
                    print(
                        "Aviso: overflow no buffer do microfone."
                    )

                audio = np.asarray(
                    audio,
                    dtype=np.int16,
                ).reshape(
                    -1
                )

                if (
                    audio.shape[0]
                    != OPENWAKEWORD_BLOCK_SAMPLES
                ):
                    print(
                        "Aviso: bloco de áudio com tamanho "
                        f"inesperado: {audio.shape[0]}"
                    )
                    continue

                ignorar_agora = bool(
                    deve_ignorar
                    and deve_ignorar()
                )

                if ignorar_agora:
                    estava_ignorando = True

                    # Descarta o áudio capturado enquanto o Orion fala.
                    continue

                if estava_ignorando:
                    # Ao voltar a escutar, começamos com o histórico limpo.
                    _resetar_modelo(
                        wake_model
                    )
                    estava_ignorando = False

                try:
                    predicoes = (
                        wake_model.predict(
                            audio
                        )
                    )
                except Exception as erro:
                    print(
                        "Erro ao processar bloco da wake word:",
                        erro,
                    )
                    _resetar_modelo(
                        wake_model
                    )
                    continue

                try:
                    score_modelo = float(
                        predicoes.get(
                            modelo_ativo,
                            0.0,
                        )
                    )
                except (TypeError, ValueError):
                    score_modelo = 0.0

                agora = time.monotonic()

                if (
                    agora - ultimo_log
                    >= 1.0
                ):
                    volume = (
                        _volume_aproximado(
                            audio
                        )
                    )

                    scores = (
                        _formatar_scores(
                            predicoes
                        )
                    )

                    print(
                        f"volume={volume:.3f} | {scores}"
                    )

                    ultimo_log = agora

                if (
                    score_modelo
                    < OPENWAKEWORD_THRESHOLD
                ):
                    continue

                if (
                    agora - ultima_deteccao
                    < WAKEWORD_COOLDOWN_SEGUNDOS
                ):
                    continue

                ultima_deteccao = agora

                print(
                    "Wake word detectada"
                )
                print(
                    "OpenWakeWord score: "
                    f"{score_modelo:.3f}"
                )

                if (
                    deve_ignorar
                    and deve_ignorar()
                ):
                    print(
                        "Wake word ignorada porque "
                        "o Orion está falando."
                    )
                    _resetar_modelo(
                        wake_model
                    )
                    continue

                # Limpa o estado antes da sessão de conversa.
                _resetar_modelo(
                    wake_model
                )

                try:
                    callback_processar_audio()
                except KeyboardInterrupt:
                    raise
                except Exception:
                    print(
                        "Erro ao processar comando "
                        "após wake word:"
                    )
                    traceback.print_exc()

                ultima_deteccao = (
                    time.monotonic()
                )

                _resetar_modelo(
                    wake_model
                )

                print(
                    "Voltando para espera"
                )
                print(
                    "Aguardando wake word..."
                )

    except KeyboardInterrupt:
        raise

    except Exception:
        print(
            "Erro no loop da wake word:"
        )
        traceback.print_exc()
        print(
            "Voltando para modo manual."
        )
        return False

    return True


def iniciar_modo_openwakeword(
    callback_processar_audio,
    deve_ignorar=None,
):
    wake_model = (
        carregar_openwakeword()
    )

    if wake_model is None:
        return False

    return detectar_loop_openwakeword(
        wake_model,
        callback_processar_audio=callback_processar_audio,
        deve_ignorar=deve_ignorar,
    )