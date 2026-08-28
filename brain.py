import re
import time

import ollama

from config import MODELO_IA, OLLAMA_SYSTEM_PROMPT
from utils import limpar_resposta_ia, limitar_resposta
from web_search import formatar_resultados, pesquisar_web, precisa_pesquisar


class OrionBrain:
    """Núcleo conversacional do Orion.

    Mantém um histórico curto de conversa e centraliza as chamadas ao modelo
    local. Contextos persistentes (memória) têm prioridade sobre o histórico
    curto para evitar que informações antigas/conflitantes contaminem a
    resposta.
    """

    MAX_HISTORICO = 6

    def __init__(self):
        self.historico = []

    def limpar_historico(self):
        self.historico = []

    @staticmethod
    def _pergunta_depende_do_contexto(pergunta):
        """Detecta continuações curtas que dependem do assunto anterior."""

        texto = str(pergunta or "").strip().lower()

        if not texto:
            return False

        padroes = (
            r"^(e|mas|então|entao|agora)\b",
            r"\b(ele|ela|eles|elas|isso|isto|esse|essa|esses|essas|"
            r"aquele|aquela|aqueles|aquelas|dele|dela|deles|delas)\b",
            r"^(quando|onde|como|por que|porque|quem)\??$",
            r"^(e\s+)?(quando|onde|como|por que|porque|quem)\b",
        )

        return any(
            re.search(padrao, texto)
            for padrao in padroes
        )

    def _salvar_historico(self, pergunta, resposta):
        self.historico.extend(
            [
                {
                    "role": "user",
                    "content": pergunta,
                },
                {
                    "role": "assistant",
                    "content": resposta,
                },
            ]
        )

        # Mantém somente as últimas mensagens para limitar contexto e latência.
        self.historico = self.historico[-self.MAX_HISTORICO :]

    def _montar_mensagens(
        self,
        pergunta,
        resultados_web=None,
        contexto_memoria=None,
    ):
        """Monta o contexto enviado ao modelo sem duplicar/recriar mensagens."""

        mensagens = [
            {
                "role": "system",
                "content": OLLAMA_SYSTEM_PROMPT,
            }
        ]

        # O histórico curto mantém a continuidade da conversa, inclusive
        # referências como "ele", "isso", "e quando?" e "mas por quê?".
        # Memórias persistentes, quando presentes, continuam tendo prioridade
        # sobre qualquer informação antiga ou conflitante do histórico.
        if self.historico:
            mensagens.extend(self.historico)

        if contexto_memoria:
            mensagens.append(
                {
                    "role": "system",
                    "content": (
                        "Memórias persistentes atuais do usuário encontradas:\n\n"
                        f"{contexto_memoria}\n\n"
                        "Estas memórias persistentes são a fonte de verdade para "
                        "a informação pessoal recuperada. Se houver conflito com "
                        "algo dito anteriormente no histórico curto, use a memória "
                        "persistente atual. Responda de forma clara, natural e "
                        "direta. Não invente detalhes ausentes. Não ofereça ajuda "
                        "adicional nem faça perguntas de acompanhamento sem "
                        "necessidade. Não diga que precisa pesquisar na internet "
                        "se a memória encontrada for suficiente."
                    ),
                }
            )

        if (
            self.historico
            and self._pergunta_depende_do_contexto(pergunta)
        ):
            mensagens.append(
                {
                    "role": "system",
                    "content": (
                        "A fala atual parece depender do contexto recente. "
                        "Resolva pronomes, referências e continuações usando "
                        "principalmente o assunto mais recente e coerente da "
                        "conversa. Exemplos de referências incluem 'ele', 'ela', "
                        "'isso', 'e quando?', 'e por quê?' e 'mas ele...'. "
                        "Não troque de assunto sem evidência. Se houver mais de "
                        "uma referência realmente possível, peça uma confirmação "
                        "curta em vez de inventar."
                    ),
                }
            )

        if resultados_web:
            mensagens.append(
                {
                    "role": "system",
                    "content": (
                        "Resultados de busca encontrados:\n"
                        f"{formatar_resultados(resultados_web)}\n\n"
                        "Para fatos provenientes da busca, responda com base nos "
                        "resultados encontrados. Não invente informações que não "
                        "estejam sustentadas por eles. Se os resultados não forem "
                        "suficientes para responder, diga isso de forma direta."
                    ),
                }
            )

        mensagens.append(
            {
                "role": "user",
                "content": pergunta,
            }
        )

        return mensagens

    @staticmethod
    def _extrair_texto_resposta(resposta):
        """Extrai o texto aceitando o formato dict e objetos do cliente Ollama."""

        if isinstance(resposta, dict):
            mensagem = resposta.get("message", {})
            if isinstance(mensagem, dict):
                return str(mensagem.get("content", "")).strip()

        mensagem = getattr(resposta, "message", None)
        if mensagem is not None:
            if isinstance(mensagem, dict):
                return str(mensagem.get("content", "")).strip()

            conteudo = getattr(mensagem, "content", "")
            return str(conteudo).strip()

        return ""

    @staticmethod
    def _resposta_parece_corrompida(texto):
        """Detecta artefatos raros de geração antes de enviar a fala ao TTS."""

        texto = str(texto or "")

        if not texto:
            return True

        if re.search(r"[，。：；！？、]", texto):
            return True

        if re.search(
           r"\b([A-Za-zÀ-ÿ]{3,})\s+\1\b",
            texto,
            flags=re.IGNORECASE,
        ):
            return True

        palavras = re.findall(r"[A-Za-zÀ-ÿ]{3,}", texto.lower())
        if len(palavras) >= 6:
            frequencia_maxima = max(palavras.count(p) for p in set(palavras))
            if frequencia_maxima / len(palavras) >= 0.45:
                return True

        return False

    def perguntar_ia(
        self,
        pergunta,
        resultados_web=None,
        contexto_memoria=None,
    ):
        pergunta = str(pergunta or "").strip()

        if not pergunta:
            return "Não entendi o que você quis dizer."

        print("Orion pensando...")

        mensagens = self._montar_mensagens(
            pergunta,
            resultados_web=resultados_web,
            contexto_memoria=contexto_memoria,
        )

        inicio_ollama = time.perf_counter()

        try:
            resposta = ollama.chat(
                model=MODELO_IA,
                messages=mensagens,
                keep_alive="30m",
                options={
                    "temperature": 0.3,
                    "top_p": 0.85,
                    "repeat_penalty": 1.08,
                    "num_predict": 120,
                    "num_ctx": 4096,
                },
            )

            tempo_ollama = time.perf_counter() - inicio_ollama
            print(f"Qwen 7B levou {tempo_ollama:.3f}s")

            texto = self._extrair_texto_resposta(resposta)

            if texto and self._resposta_parece_corrompida(texto):
                print("Resposta do 7B com artefatos. Regenerando uma vez...")

                mensagens_retry = list(mensagens)
                mensagens_retry.append(
                    {
                        "role": "system",
                        "content": (
                            "A resposta anterior saiu corrompida. Responda novamente "
                            "em português do Brasil, de forma natural, em no máximo "
                            "duas frases, sem caracteres estranhos nem repetições."
                        ),
                    }
                )

                resposta_retry = ollama.chat(
                    model=MODELO_IA,
                    messages=mensagens_retry,
                    keep_alive="30m",
                    options={
                        "temperature": 0.1,
                        "top_p": 0.75,
                        "repeat_penalty": 1.12,
                        "num_predict": 90,
                        "num_ctx": 4096,
                    },
                )

                texto_retry = self._extrair_texto_resposta(
                    resposta_retry
                )

                if texto_retry:
                    texto = texto_retry

            if not texto:
                print("Ollama retornou uma resposta vazia.")
                return "Minha IA local respondeu sem conteúdo. Tente novamente."

            texto = limitar_resposta(
                limpar_resposta_ia(texto),
                max_frases=3,
                max_chars=500,
            )

            if not texto:
                print("A resposta ficou vazia após o processamento.")
                return "Minha IA local respondeu sem conteúdo. Tente novamente."

            self._salvar_historico(pergunta, texto)
            return texto

        except Exception as erro:
            tempo_ollama = time.perf_counter() - inicio_ollama
            print(f"Qwen 7B falhou após {tempo_ollama:.3f}s")
            print("Erro ao consultar Ollama:", erro)
            return "Não consegui acessar minha IA local agora."

    @staticmethod
    def _extrair_conteudo_memoria(conteudo):
        """
        Extrai apenas o corpo útil de uma memória Markdown.

        Remove:
        - título Markdown (# ...)
        - separador ---
        - metadados "Criado pelo Orion..." / "Atualizado pelo Orion..."
        """
        linhas = str(conteudo or "").splitlines()
        corpo = []

        for linha in linhas:
            linha_limpa = linha.strip()

            if not linha_limpa:
                continue

            if linha_limpa.startswith("#"):
                continue

            if linha_limpa == "---":
                break

            if linha_limpa.lower().startswith(
                ("criado pelo orion em ", "atualizado pelo orion em ")
            ):
                continue

            corpo.append(linha_limpa)

        return " ".join(corpo).strip()

    @staticmethod
    def _resposta_direta_memoria(conteudo):
        """
        Responde uma memória única sem passar pelo LLM.

        Converte memórias salvas na perspectiva do usuário para a perspectiva
        do Orion. Exemplo:
            "meu editor favorito é VS Code"
        vira:
            "Seu editor favorito é VS Code."

        Mantém a resposta determinística para evitar alucinações do modelo.
        """
        conteudo = str(conteudo or "").strip()

        if not conteudo:
            return ""

        # Normaliza somente espaços; preserva nomes, siglas e acentuação.
        conteudo = re.sub(
            r"\s+",
            " ",
            conteudo,
        ).strip()

        # Corrige uma forma comum criada pelo fluxo de atualização atual:
        # "meu editor favorito e vscode" -> "meu editor favorito é vscode"
        # Só aplica quando "e" funciona claramente como verbo de ligação.
        conteudo = re.sub(
            r"^(o\s+)?(meu|minha|meus|minhas)\s+(.+?)\s+e\s+(.+)$",
            lambda m: (
                f"{m.group(1) or ''}{m.group(2)} "
                f"{m.group(3)} é {m.group(4)}"
            ),
            conteudo,
            flags=re.IGNORECASE,
        )

        # Remove artigo inicial antes de possessivo:
        # "o meu editor..." -> "meu editor..."
        conteudo = re.sub(
            r"^(o|a|os|as)\s+(meu|minha|meus|minhas)\b",
            r"\2",
            conteudo,
            flags=re.IGNORECASE,
        )

        # Troca apenas o possessivo inicial para manter a perspectiva correta.
        substituicoes = (
            (r"^meu\b", "Seu"),
            (r"^minha\b", "Sua"),
            (r"^meus\b", "Seus"),
            (r"^minhas\b", "Suas"),
        )

        resposta = conteudo

        for padrao, substituto in substituicoes:
            resposta_nova = re.sub(
                padrao,
                substituto,
                resposta,
                count=1,
                flags=re.IGNORECASE,
            )

            if resposta_nova != resposta:
                resposta = resposta_nova
                break

        if resposta[-1] not in ".!?":
            resposta += "."

        return resposta

    def responder_com_memoria(self, pergunta, memorias):
        """Usa memórias encontradas no Vault do Obsidian como contexto."""

        if not memorias:
            return "Não encontrei nenhuma memória relacionada a isso."

        memorias_validas = []

        for memoria in memorias:
            if not isinstance(memoria, dict):
                continue

            titulo = memoria.get("titulo", "Sem título")
            categoria = memoria.get("categoria", "desconhecida")
            conteudo_bruto = str(memoria.get("conteudo", "")).strip()

            if not conteudo_bruto:
                continue

            conteudo = self._extrair_conteudo_memoria(
                conteudo_bruto
            )

            if not conteudo:
                continue

            memorias_validas.append(
                {
                    "titulo": titulo,
                    "categoria": categoria,
                    "conteudo": conteudo,
                }
            )

        if not memorias_validas:
            return "Não encontrei nenhuma memória relacionada a isso."

        print(
            f"Usando {len(memorias_validas)} memória(s) persistente(s)."
        )

        # Caso comum: a busca encontrou um único fato objetivo.
        # Não há motivo para pedir ao LLM para "interpretar" algo já conhecido.
        if len(memorias_validas) == 1:
            resposta = self._resposta_direta_memoria(
                memorias_validas[0]["conteudo"]
            )

            if resposta:
                self._salvar_historico(
                    pergunta,
                    resposta,
                )
                return resposta

        # Quando há várias memórias relevantes, o LLM ainda é útil para
        # sintetizar a resposta, mas recebe apenas o conteúdo limpo.
        blocos = []

        for memoria in memorias_validas:
            blocos.append(
                f"Título: {memoria['titulo']}\n"
                f"Categoria: {memoria['categoria']}\n"
                f"Conteúdo: {memoria['conteudo']}"
            )

        contexto_memoria = "\n\n---\n\n".join(blocos)

        return self.perguntar_ia(
            pergunta,
            contexto_memoria=contexto_memoria,
        )

    def responder_com_busca(self, pergunta):
        print("Pesquisando na web...")
        inicio_busca = time.perf_counter()

        try:
            resultados = pesquisar_web(pergunta)
        except Exception as erro:
            tempo_busca = time.perf_counter() - inicio_busca
            print(f"Busca web falhou após {tempo_busca:.3f}s")
            print("Erro durante a busca web:", erro)
            print("Usando apenas a IA local.")
            return self.perguntar_ia(pergunta)

        tempo_busca = time.perf_counter() - inicio_busca
        print(f"Busca web levou {tempo_busca:.3f}s")

        if not resultados:
            print("Nenhum resultado útil encontrado. Usando apenas a IA local.")
            return self.perguntar_ia(pergunta)

        return self.perguntar_ia(
            pergunta,
            resultados_web=resultados,
        )

    def responder(self, pergunta):
        pergunta = str(pergunta or "").strip()

        if not pergunta:
            return "Não entendi o que você quis dizer."

        inicio_total = time.perf_counter()

        try:
            deve_pesquisar = precisa_pesquisar(pergunta)
        except Exception as erro:
            print("Erro ao decidir se a pergunta precisa de busca web:", erro)
            deve_pesquisar = False

        if deve_pesquisar:
            resposta = self.responder_com_busca(pergunta)
        else:
            resposta = self.perguntar_ia(pergunta)

        tempo_total = time.perf_counter() - inicio_total
        print(f"Brain total: {tempo_total:.3f}s")

        return resposta