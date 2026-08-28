import time
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from config import ROKU_TV_IP, ROKU_TV_PORT


class RokuTVController:
    def __init__(
        self,
        ip=None,
        port=None,
        timeout=3.0,
    ):
        self.ip = ip or ROKU_TV_IP

        if not self.ip:
            raise ValueError(
                "ROKU_TV_IP não configurado no .env."
            )

        self.port = int(
            port
            or ROKU_TV_PORT
        )

        self.timeout = float(timeout)

        self.base_url = (
            f"http://{self.ip}:{self.port}"
        )

    # =========================================================
    # HTTP / ECP
    # =========================================================

    def _get(self, endpoint):
        url = (
            self.base_url
            + "/"
            + endpoint.lstrip("/")
        )

        try:
            with urllib.request.urlopen(
                url,
                timeout=self.timeout,
            ) as resposta:
                return resposta.read().decode(
                    "utf-8",
                    errors="replace",
                )

        except urllib.error.URLError as erro:
            raise ConnectionError(
                f"Não consegui acessar a Roku TV em {self.base_url}: {erro}"
            ) from erro

    def _post(self, endpoint):
        url = (
            self.base_url
            + "/"
            + endpoint.lstrip("/")
        )

        requisicao = urllib.request.Request(
            url,
            method="POST",
            data=b"",
        )

        try:
            with urllib.request.urlopen(
                requisicao,
                timeout=self.timeout,
            ) as resposta:
                return resposta.status in (
                    200,
                    202,
                    204,
                )

        except urllib.error.URLError as erro:
            raise ConnectionError(
                f"Não consegui enviar comando para a Roku TV: {erro}"
            ) from erro

    # =========================================================
    # INFORMAÇÕES
    # =========================================================

    def device_info(self):
        xml = self._get(
            "query/device-info"
        )

        raiz = ET.fromstring(xml)

        info = {}

        for filho in raiz:
            info[filho.tag] = (
                filho.text or ""
            ).strip()

        return info

    def esta_ligada(self):
        try:
            info = self.device_info()
        except Exception:
            return False

        modo = (
            info.get("power-mode", "")
            .strip()
            .lower()
        )

        return modo == "poweron"

    def garantir_ligada(
        self,
        timeout=10.0,
        intervalo=0.25,
    ):
        """
        Garante que a TV esteja ligada e pronta para receber comandos.

        Se já estiver ligada, retorna imediatamente.
        Se estiver desligada, envia PowerOn e consulta o estado até
        a TV responder como PowerOn ou o tempo limite terminar.
        """
        if self.esta_ligada():
            return True

        try:
            self.power_on()
        except Exception as erro:
            print(
                "Erro ao enviar PowerOn para a TV:",
                erro,
            )
            return False

        limite = time.monotonic() + float(timeout)

        while time.monotonic() < limite:
            if self.esta_ligada():
                return True

            time.sleep(float(intervalo))

        return False

    def _executar_se_ligada(
        self,
        acao,
        mensagem_sucesso,
        mensagem_erro,
    ):
        """
        Executa comandos comuns apenas quando a TV está ligada.

        Evita esperar o timeout completo em comandos como volume,
        Home ou abertura de apps quando a TV está desligada.
        """
        if not self.esta_ligada():
            return "A TV está desligada."

        try:
            resultado = acao()

            if resultado is False:
                return mensagem_erro

            return mensagem_sucesso

        except Exception as erro:
            print(
                "Erro ao controlar TV:",
                erro,
            )
            return mensagem_erro

    # =========================================================
    # BOTÕES / NAVEGAÇÃO
    # =========================================================

    def keypress(self, tecla):
        tecla = str(
            tecla or ""
        ).strip()

        if not tecla:
            return False

        return self._post(
            f"keypress/{tecla}"
        )

    def home(self):
        return self.keypress("Home")

    def up(self):
        return self.keypress("Up")

    def down(self):
        return self.keypress("Down")

    def left(self):
        return self.keypress("Left")

    def right(self):
        return self.keypress("Right")

    def select(self):
        return self.keypress("Select")

    def back(self):
        return self.keypress("Back")

    # =========================================================
    # MÍDIA
    # =========================================================

    def play_pause(self):
        return self.keypress("Play")

    def rewind(self):
        return self.keypress("Rev")

    def forward(self):
        return self.keypress("Fwd")

    # =========================================================
    # VOLUME
    # =========================================================

    def volume_up(self):
        return self.keypress("VolumeUp")

    def volume_down(self):
        return self.keypress("VolumeDown")

    def mute(self):
        return self.keypress("VolumeMute")

    # =========================================================
    # ENERGIA
    # =========================================================

    def power_on(self):
        return self.keypress("PowerOn")

    def power_off(self):
        return self.keypress("PowerOff")

    def power_toggle(self):
        return self.keypress("Power")

    # =========================================================
    # APPS
    # =========================================================

    def listar_apps(self):
        xml = self._get(
            "query/apps"
        )

        raiz = ET.fromstring(xml)

        apps = []

        for app in raiz.findall("app"):
            nome = (
                app.text or ""
            ).strip()

            app_id = (
                app.attrib.get("id", "")
                or ""
            ).strip()

            if not nome or not app_id:
                continue

            apps.append(
                {
                    "nome": nome,
                    "id": app_id,
                    "tipo": app.attrib.get(
                        "type",
                        "",
                    ),
                    "versao": app.attrib.get(
                        "version",
                        "",
                    ),
                }
            )

        return apps

    def encontrar_app(self, nome):
        alvo = str(
            nome or ""
        ).strip().lower()

        if not alvo:
            return None

        apps = self.listar_apps()

        for app in apps:
            if app["nome"].lower() == alvo:
                return app

        for app in apps:
            if alvo in app["nome"].lower():
                return app

        return None

    def abrir_app(self, nome):
        app = self.encontrar_app(
            nome
        )

        if not app:
            return False

        return self._post(
            f"launch/{app['id']}"
        )

    # =========================================================
    # RESPOSTAS AMIGÁVEIS PARA O ORION
    # =========================================================

    def comando_ligar(self):
        try:
            self.power_on()
            return "Ligando a TV."

        except Exception as erro:
            print(
                "Erro ao ligar TV:",
                erro,
            )
            return "Não consegui ligar a TV."

    def comando_desligar(self):
        return self._executar_se_ligada(
            self.power_off,
            "Desligando a TV.",
            "Não consegui desligar a TV.",
        )

    def comando_volume_up(self):
        return self._executar_se_ligada(
            self.volume_up,
            "Aumentei o volume da TV.",
            "Não consegui aumentar o volume da TV.",
        )

    def comando_volume_down(self):
        return self._executar_se_ligada(
            self.volume_down,
            "Abaixei o volume da TV.",
            "Não consegui abaixar o volume da TV.",
        )

    def comando_mute(self):
        return self._executar_se_ligada(
            self.mute,
            "Mutei a TV.",
            "Não consegui mutar a TV.",
        )

    def comando_home(self):
        return self._executar_se_ligada(
            self.home,
            "Abri a tela inicial da TV.",
            "Não consegui abrir a tela inicial da TV.",
        )

    def comando_abrir_app(self, nome):
        nome = str(nome or "").strip()

        if not nome:
            return "Qual aplicativo você quer abrir na TV?"

        if not self.garantir_ligada():
            return "Não consegui ligar a TV."

        try:
            if self.abrir_app(nome):
                return f"Abrindo {nome} na TV."

            return (
                f"Não encontrei {nome} instalado na TV."
            )

        except Exception as erro:
            print(
                f"Erro ao abrir {nome} na TV:",
                erro,
            )
            return (
                f"Não consegui abrir {nome} na TV."
            )