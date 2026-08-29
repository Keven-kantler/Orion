import time
import traceback

from audio_recorder import ManualAudioRecorder
from brain import OrionBrain
from commands import processar_texto_usuario
from config import MODO_ATIVACAO, WAKEWORD_ENGINE
from spotify_controller import SpotifyController
from stt import WhisperTranscriber
from tts import OrionSpeaker
from wakeword_openwakeword import iniciar_modo_openwakeword


def _audio_vazio(audio):
    """
    Verifica de forma segura se um áudio está vazio.

    Os gravadores atuais retornam numpy.ndarray, mas esta verificação evita
    que um retorno inesperado (como None) derrube o Orion inteiro.
    """
    if audio is None:
        return True

    return getattr(audio, "size", 0) == 0


def _registrar_erro(etapa, erro):
    """
    Registra a exceção completa no terminal sem encerrar o Orion.

    A intenção é que uma falha pontual de STT, roteamento, dispositivo ou
    serviço externo não derrube toda a sessão.
    """
    print(f"Erro durante {etapa}: {erro}")
    traceback.print_exc()


def processar_audio_gravado(
    audio,
    transcriber,
    brain,
    spotify,
    speaker,
    texto_pretranscrito=None,
):
    """
    Processa um áudio gravado.

    Retorna:
        True  -> encontrou e processou um comando.
        False -> áudio vazio, transcrição sem conteúdo ou falha pontual.

    Uma falha durante um único comando é isolada aqui para que o processo
    principal do Orion continue ativo.
    """
    if _audio_vazio(audio):
        return False

    print("Processando áudio...")

    if texto_pretranscrito:
        texto = str(texto_pretranscrito).strip()
        print("Usando transcrição já validada no fim da fala.")
    else:
        try:
            texto = transcriber.transcrever_audio(audio)
        except Exception as erro:
            _registrar_erro("transcrição do áudio", erro)
            return False

    if not texto:
        print("Não entendi nada útil.")
        return False

    texto = str(texto).strip()

    if len(texto) < 3:
        print("Não entendi nada útil.")
        return False

    print(f"Texto transcrito: {texto}")

    try:
        resposta = processar_texto_usuario(
            texto,
            brain,
            spotify,
        )
    except Exception as erro:
        _registrar_erro("processamento do comando", erro)
        return False

    if resposta:
        try:
            speaker.falar(resposta)
        except Exception as erro:
            # OrionSpeaker já trata internamente as falhas atuais, mas esta
            # proteção mantém o main seguro caso a implementação mude.
            _registrar_erro("síntese de voz", erro)

    return True


def esperar_orion_terminar_de_falar(speaker):
    """
    Impede o microfone de começar a ouvir enquanto o Orion ainda está falando.
    """
    while speaker.esta_falando():
        time.sleep(0.1)


def executar_modo_manual(
    recorder,
    transcriber,
    brain,
    spotify,
    speaker,
):
    print("Modo manual ativo.")
    print("Pressione seta para baixo para começar a gravar.")
    print("Pressione seta para baixo novamente para parar.")

    while True:
        if speaker.esta_falando():
            time.sleep(0.2)
            continue

        print("\nAguardando comando de voz...")

        try:
            recorder.esperar_toggle()
        except Exception as erro:
            _registrar_erro("espera do comando manual", erro)
            time.sleep(0.2)
            continue

        if speaker.esta_falando():
            print("Ignorando gravação enquanto o Orion fala.")
            time.sleep(0.2)
            continue

        try:
            audio = recorder.gravar_ate_toggle(
                deve_bloquear=speaker.esta_falando
            )
        except Exception as erro:
            _registrar_erro("gravação manual", erro)
            time.sleep(0.2)
            continue

        processar_audio_gravado(
            audio,
            transcriber,
            brain,
            spotify,
            speaker,
        )


def executar_sessao_conversa(
    recorder,
    transcriber,
    brain,
    spotify,
    speaker,
):
    """
    Mantém o Orion ouvindo novos comandos sem exigir a wake word novamente.

    A sessão termina quando nenhum novo comando for detectado dentro do tempo
    máximo de gravação ou quando uma falha pontual impede o comando atual de
    ser processado.
    """
    print("")
    print("Sessão de conversa ativa.")
    print("Pode continuar falando sem dizer a wake word.")

    while True:
        esperar_orion_terminar_de_falar(speaker)

        print("")
        print("Aguardando próximo comando...")

        try:
            audio, texto_pretranscrito = recorder.gravar_ate_silencio(
                deve_bloquear=speaker.esta_falando,
                transcrever_parcial=transcriber.transcrever_audio,
            )
        except Exception as erro:
            _registrar_erro("gravação da sessão de conversa", erro)
            print("Sessão encerrada.")
            return

        if _audio_vazio(audio):
            print("")
            print("Nenhum novo comando detectado.")
            print("Sessão encerrada.")
            return

        comando_processado = processar_audio_gravado(
            audio,
            transcriber,
            brain,
            spotify,
            speaker,
            texto_pretranscrito=texto_pretranscrito,
        )

        if not comando_processado:
            print("")
            print("Sessão encerrada.")
            return


def executar_modo_wakeword(
    recorder,
    transcriber,
    brain,
    spotify,
    speaker,
):
    def gravar_comando_apos_wakeword():
        if speaker.esta_falando():
            print("Ignorando wake word enquanto o Orion fala.")
            return

        # PRIMEIRO COMANDO
        print("Gravando comando...")

        try:
            audio, texto_pretranscrito = recorder.gravar_ate_silencio(
                deve_bloquear=speaker.esta_falando,
                transcrever_parcial=transcriber.transcrever_audio,
            )
        except Exception as erro:
            _registrar_erro("gravação após wake word", erro)
            return

        comando_processado = processar_audio_gravado(
            audio,
            transcriber,
            brain,
            spotify,
            speaker,
            texto_pretranscrito=texto_pretranscrito,
        )

        if not comando_processado:
            print("Nenhum comando detectado.")
            return

        # MODO CONVERSA
        executar_sessao_conversa(
            recorder,
            transcriber,
            brain,
            spotify,
            speaker,
        )

        print("")
        print("Voltando para espera da wake word.")

    try:
        return iniciar_modo_openwakeword(
            callback_processar_audio=gravar_comando_apos_wakeword,
            deve_ignorar=speaker.esta_falando,
        )
    except Exception as erro:
        # O módulo de wake word atual já possui seu próprio fallback, porém
        # esta barreira evita que uma falha inesperada impeça o modo manual.
        _registrar_erro("modo wake word", erro)
        return False


def _inicializar_componentes():
    """
    Inicializa os componentes centrais em um único lugar.

    Mantém exatamente as mesmas classes usadas pelo Orion atual e facilita
    diagnosticar em qual etapa uma falha de inicialização ocorreu.
    """
    print("Inicializando voz...")
    speaker = OrionSpeaker()

    print("Inicializando gravador...")
    recorder = ManualAudioRecorder()

    print("Inicializando Whisper...")
    transcriber = WhisperTranscriber()

    print("Inicializando cérebro...")
    brain = OrionBrain()

    print("Inicializando Spotify...")
    spotify = SpotifyController()

    return recorder, transcriber, brain, spotify, speaker


def main():
    print("Orion iniciado.")
    print("CTRL + C para desligar.\n")

    recorder = None
    listener_iniciado = False

    try:
        (
            recorder,
            transcriber,
            brain,
            spotify,
            speaker,
        ) = _inicializar_componentes()

        recorder.iniciar_listener()
        listener_iniciado = True

        if (
            MODO_ATIVACAO == "wakeword"
            and WAKEWORD_ENGINE == "openwakeword"
        ):
            print("Modo wake word experimental ativo.")

            iniciado = executar_modo_wakeword(
                recorder,
                transcriber,
                brain,
                spotify,
                speaker,
            )

            if not iniciado:
                print("Wake word indisponível. Ativando modo manual.")

                executar_modo_manual(
                    recorder,
                    transcriber,
                    brain,
                    spotify,
                    speaker,
                )
        else:
            executar_modo_manual(
                recorder,
                transcriber,
                brain,
                spotify,
                speaker,
            )

    except KeyboardInterrupt:
        print("\nDesligando Orion...")

    except Exception as erro:
        # Erros de inicialização são diferentes de falhas de um único comando:
        # sem os componentes centrais não é seguro fingir que o Orion iniciou.
        _registrar_erro("inicialização/execução principal", erro)

    finally:
        if recorder is not None and listener_iniciado:
            try:
                recorder.parar_listener()
            except Exception as erro:
                _registrar_erro("encerramento do listener", erro)

        print("Orion desligado.")


if __name__ == "__main__":
    main()