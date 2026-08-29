import re



SYSTEM_PROMPT_MEMORY = """
Você é o analisador de memória automática do assistente Orion.

Sua única função é decidir se uma mensagem normal do usuário
contém informação duradoura e útil para conversas futuras.

Você NÃO responde ao usuário.
Você NÃO inventa informações.
Retorne somente JSON válido.

Formato:

{
  "salvar": true ou false,
  "categoria": "perfil|projetos|conhecimento|ideias|notas",
  "titulo": "título curto",
  "conteudo": "fato objetivo"
}

Se não valer a pena salvar:

{
  "salvar": false,
  "categoria": "",
  "titulo": "",
  "conteudo": ""
}

CATEGORIAS:

perfil:
- nome e identidade do usuário;
- relações pessoais;
- nomes de pessoas próximas;
- preferências e favoritos;
- rotina estável;
- cidade, estudo, trabalho;
- gostos e aversões duradouras.

projetos:
- tecnologias usadas em um projeto;
- arquitetura;
- estado atual de desenvolvimento;
- decisões técnicas concretas.

ideias:
- recursos desejados no futuro;
- funcionalidades ainda planejadas;
- ideias ainda não implementadas.

conhecimento:
- informação duradoura que o usuário explicitamente estabeleceu
  como referência útil, mas que não é perfil nem projeto.

notas:
- informação duradoura útil que não encaixe melhor acima.

NÃO SALVE:
- perguntas;
- comandos;
- conversa casual;
- saudações;
- fatos temporários;
- clima;
- horário;
- pedidos de música;
- pesquisas;
- respostas do Orion;
- informações inferidas que o usuário não afirmou.

NUNCA SALVE AUTOMATICAMENTE:
- senhas;
- tokens;
- chaves de API;
- códigos de autenticação;
- dados bancários;
- números de documentos;
- credenciais.

Se houver dúvida, prefira salvar=false.
"""


CATEGORIAS_PERMITIDAS = {
    "perfil",
    "projetos",
    "conhecimento",
    "ideias",
    "notas",
}


class MemoryAnalyzer:
    def __init__(self, cliente_ollama=None):
        # Mantém a assinatura compatível com versões anteriores.
        # O analisador automático agora é 100% determinístico e não usa LLM.
        self._ollama = cliente_ollama

    @staticmethod
    def _vazio():
        return {
            "salvar": False,
            "categoria": "",
            "titulo": "",
            "conteudo": "",
        }

    @staticmethod
    def _titulo_do_texto(texto):
        titulo = str(texto or "").strip()[:60]
        if len(str(texto or "").strip()) > 60:
            titulo = titulo.rstrip(" ,.;:-") + "..."
        return titulo

    @staticmethod
    def _coagir_bool(valor):
        """
        Evita o bug bool("false") == True.

        Aceita apenas representações explícitas de verdadeiro.
        """
        if isinstance(valor, bool):
            return valor

        if isinstance(valor, (int, float)):
            return valor == 1

        if isinstance(valor, str):
            return valor.strip().lower() in {
                "true",
                "1",
                "sim",
                "yes",
            }

        return False

    @staticmethod
    def _contem_dado_sensivel(texto):
        """
        Bloqueia memória automática quando a mensagem parece conter
        uma credencial ou um dado pessoal/bancário explícito.

        O filtro procura a presença de um VALOR associado ao dado sensível,
        para não bloquear frases conceituais como:
        "quero adicionar suporte a tokens no Orion".
        """
        texto = str(texto or "").strip()

        if not texto:
            return False

        padroes = (
            r"\b(?:minha|meu|a|o)?\s*(?:senha|password)\s*(?:é|e|:|=)\s*\S+",
            r"\b(?:meu|minha)?\s*(?:token|access token|refresh token)\s*(?:é|e|:|=)\s*\S+",
            r"\b(?:minha|meu)?\s*(?:chave de api|api key|client secret|client_secret)\s*(?:é|e|:|=)\s*\S+",
            r"\b(?:meu|minha)?\s*(?:código|codigo)\s+(?:de\s+)?(?:autenticação|autenticacao|verificação|verificacao|2fa|otp)\s*(?:é|e|:|=)\s*\S+",
            r"\b(?:meu|minha)?\s*(?:cpf|cnpj|rg|passaporte)\s*(?:é|e|:|=)\s*[A-Za-z0-9.\-/]+",
            r"\b(?:meu|minha)?\s*(?:cartão|cartao|cvv)\s*(?:é|e|:|=)\s*[A-Za-z0-9 .\-]+",
            r"\b(?:minha|meu)?\s*(?:conta bancária|conta bancaria|agência|agencia|chave pix)\s*(?:é|e|:|=)\s*\S+",
        )

        if any(
            re.search(padrao, texto, flags=re.IGNORECASE)
            for padrao in padroes
        ):
            return True

        # Formatos comuns de segredos que não devem ir para memória mesmo
        # se o usuário não disser explicitamente "minha chave é...".
        formatos_secretos = (
            r"\bsk-[A-Za-z0-9_-]{12,}\b",
            r"\bgh[pousr]_[A-Za-z0-9]{20,}\b",
        )

        return any(
            re.search(padrao, texto, flags=re.IGNORECASE)
            for padrao in formatos_secretos
        )

    def _analisar_deterministico(self, texto):
        texto_limpo = str(texto or "").strip()
        texto_norm = texto_limpo.lower()

        if not texto_limpo:
            return self._vazio()

        if self._contem_dado_sensivel(texto_limpo):
            print("Memory Analyzer: ignorar dado sensível.")
            return self._vazio()

        prefixos_pergunta = (
            "qual ",
            "quais ",
            "quem ",
            "o que ",
            "onde ",
            "quando ",
            "como ",
            "por que ",
            "porque ",
            "voce lembra",
            "você lembra",
        )

        if texto_limpo.endswith("?") or texto_norm.startswith(prefixos_pergunta):
            return self._vazio()

        # Frases conversacionais/comparativas não são memória duradoura.
        # Ex.: "eu queria comparar com java", "acho que python é melhor aqui".
        prefixos_conversa = (
            "eu queria ",
            "queria ",
            "eu quero saber ",
            "quero saber ",
            "acho que ",
            "talvez ",
            "entao ",
            "então ",
            "mas ",
            "e ",
        )

        termos_conversa = (
            " comparar ",
            " comparação ",
            " comparacao ",
            " diferença ",
            " diferenca ",
            " explicar ",
            " explicação ",
            " explicacao ",
        )

        if (
            texto_norm.startswith(prefixos_conversa)
            or any(termo in f" {texto_norm} " for termo in termos_conversa)
        ):
            return self._vazio()

        prefixos_comando = (
            "toca ",
            "toque ",
            "abre ",
            "abra ",
            "pesquisa ",
            "pesquise ",
            "procura ",
            "procure ",
            "esquece ",
            "esqueça ",
            "corrija ",
            "corrige ",
        )

        if texto_norm.startswith(prefixos_comando):
            return self._vazio()

        padroes = (
            (
                "perfil",
                r"^(?:o\s+)?meu\s+.+\s+(?:favorito|favorita|preferido|preferida)\s+(?:e|é)\s+.+$",
            ),
            (
                "perfil",
                r"^(?:a\s+)?minha\s+.+\s+(?:favorita|preferida)\s+(?:e|é)\s+.+$",
            ),
            (
                "perfil",
                r"^meu nome\s+(?:e|é)\s+.+$",
            ),
            (
                "perfil",
                r"^o nome d[ao] minh[ao]\s+.+\s+(?:e|é)\s+.+$",
            ),
            (
                "projetos",
                r"^estou\s+(?:desenvolvendo|criando|fazendo|trabalhando)\s+.+$",
            ),
            (
                "ideias",
                r"^quero\s+(?:adicionar|colocar|criar|implementar)\s+.+$",
            ),
        )

        for categoria, padrao in padroes:
            if re.search(
                padrao,
                texto_norm,
                flags=re.IGNORECASE,
            ):
                return {
                    "salvar": True,
                    "categoria": categoria,
                    "titulo": self._titulo_do_texto(texto_limpo),
                    "conteudo": texto_limpo,
                }

        return None

    def analisar(self, texto):
        """
        Analisa memória automática de forma conservadora e determinística.

        Regra principal:
        - só salva quando a própria fala do usuário corresponde a um padrão
          explícito de informação duradoura;
        - perguntas, comandos, conversa casual e frases ambíguas são ignoradas;
        - não consulta LLM, evitando falsos positivos e competição por RAM/VRAM.
        """
        texto = str(texto or "").strip()
        vazio = self._vazio()

        if not texto:
            return vazio

        # Segurança vem antes de qualquer tentativa de salvar.
        if self._contem_dado_sensivel(texto):
            print("Memory Analyzer: ignorar dado sensível.")
            return vazio

        resultado = self._analisar_deterministico(texto)

        if not isinstance(resultado, dict) or not resultado.get("salvar"):
            print("Memory Analyzer: ignorar | determinístico")
            return vazio

        print(
            "Memory Analyzer: salvar "
            f"| {resultado['categoria']} "
            f"| {resultado['titulo']} "
            "| determinístico"
        )
        return resultado
