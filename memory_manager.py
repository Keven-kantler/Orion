from datetime import datetime
from pathlib import Path
import os
import re
import tempfile
import unicodedata

from config import PASTA_ORION


class MemoryManager:
    CATEGORIAS = (
        "perfil",
        "projetos",
        "conhecimento",
        "ideias",
        "notas",
        "conversas",
    )

    NOMES_PASTAS = {
        "perfil": "Perfil",
        "projetos": "Projetos",
        "conhecimento": "Conhecimento",
        "ideias": "Ideias",
        "notas": "Notas",
        "conversas": "Conversas",
    }

    CARACTERES_INVALIDOS_WINDOWS = '<>:"/\\|?*'

    def __init__(self, pasta_memoria=None):
        """
        Gerencia a memória persistente do Orion em arquivos Markdown.

        Se `pasta_memoria` não for informado, o vault fica dentro da pasta
        real do Orion definida em config.PASTA_ORION. Isso mantém os testes
        com TemporaryDirectory funcionando e remove a dependência fixa de
        C:\\Orion.
        """
        if pasta_memoria is None:
            pasta_memoria = Path(PASTA_ORION) / "Orion Memory"

        self.pasta_memoria = Path(pasta_memoria).expanduser()

        self.pastas = {
            categoria: self.pasta_memoria / nome_pasta
            for categoria, nome_pasta in self.NOMES_PASTAS.items()
        }

        self._criar_estrutura()

    # =========================================================
    # ESTRUTURA E UTILITÁRIOS
    # =========================================================

    def _criar_estrutura(self):
        """
        Cria automaticamente a estrutura da memória.
        """
        self.pasta_memoria.mkdir(
            parents=True,
            exist_ok=True,
        )

        for pasta in self.pastas.values():
            pasta.mkdir(
                parents=True,
                exist_ok=True,
            )

    def _normalizar_categoria(self, categoria, padrao="notas"):
        categoria = str(categoria or "").strip().lower()

        if categoria in self.pastas:
            return categoria

        return padrao

    def _normalizar_texto(self, texto):
        """
        Normaliza texto para comparação.

        Exemplo:
        "Reconhecimento Facial"
        -> "reconhecimento facial"
        """
        texto = str(texto or "").lower()

        texto = unicodedata.normalize(
            "NFKD",
            texto,
        )

        texto = "".join(
            caractere
            for caractere in texto
            if not unicodedata.combining(caractere)
        )

        texto = re.sub(
            r"[^a-z0-9\s]",
            " ",
            texto,
        )

        texto = re.sub(
            r"\s+",
            " ",
            texto,
        )

        return texto.strip()

    def _titulo_seguro(self, titulo, fallback="Nota"):
        """
        Gera um nome de arquivo seguro para Windows sem alterar o título
        exibido dentro do Markdown.
        """
        titulo = str(titulo or "").strip()

        titulo_seguro = "".join(
            caractere
            for caractere in titulo
            if caractere not in self.CARACTERES_INVALIDOS_WINDOWS
        )

        # Windows não aceita nomes terminando em ponto/espaço.
        titulo_seguro = titulo_seguro.strip().rstrip(". ")

        # Evita nomes especiais reservados no Windows.
        nomes_reservados = {
            "CON",
            "PRN",
            "AUX",
            "NUL",
            *(f"COM{i}" for i in range(1, 10)),
            *(f"LPT{i}" for i in range(1, 10)),
        }

        if titulo_seguro.upper() in nomes_reservados:
            titulo_seguro = f"{titulo_seguro}_"

        if not titulo_seguro:
            titulo_seguro = fallback

        # Evita nomes absurdamente longos e deixa margem para o caminho
        # completo do Windows.
        return titulo_seguro[:120].rstrip(". ") or fallback

    def _caminho_disponivel(self, pasta, titulo_seguro, ignorar=None):
        """
        Retorna um caminho que não sobrescreve outra memória existente.

        `ignorar` é usado durante atualização: o próprio arquivo antigo pode
        ser reutilizado quando o novo título resultar no mesmo caminho.
        """
        pasta = Path(pasta)
        ignorar_resolvido = None

        if ignorar is not None:
            try:
                ignorar_resolvido = Path(ignorar).resolve()
            except OSError:
                ignorar_resolvido = Path(ignorar)

        candidato = pasta / f"{titulo_seguro}.md"

        def disponivel(caminho):
            if not caminho.exists():
                return True

            if ignorar_resolvido is None:
                return False

            try:
                return caminho.resolve() == ignorar_resolvido
            except OSError:
                return caminho == Path(ignorar)

        if disponivel(candidato):
            return candidato

        indice = 2

        while True:
            candidato = pasta / f"{titulo_seguro} ({indice}).md"

            if disponivel(candidato):
                return candidato

            indice += 1

    def _escrever_atomico(self, arquivo, texto):
        """
        Grava primeiro em arquivo temporário e só depois substitui o destino.
        Assim uma interrupção durante a escrita reduz o risco de deixar uma
        memória Markdown parcialmente escrita/corrompida.
        """
        arquivo = Path(arquivo)
        arquivo.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temporario = None

        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                newline="\n",
                delete=False,
                dir=str(arquivo.parent),
                prefix=f".{arquivo.stem}.",
                suffix=".tmp",
            ) as handle:
                handle.write(texto)
                handle.flush()
                os.fsync(handle.fileno())
                temporario = Path(handle.name)

            os.replace(
                str(temporario),
                str(arquivo),
            )

        finally:
            if temporario is not None and temporario.exists():
                try:
                    temporario.unlink()
                except OSError:
                    pass

    def _ler_arquivo(self, arquivo):
        try:
            return Path(arquivo).read_text(
                encoding="utf-8"
            )
        except (OSError, UnicodeError) as erro:
            print(
                f"Erro ao ler memória {arquivo}:",
                erro,
            )
            return None

    def _extrair_termos_busca(self, consulta):
        """
        Extrai palavras relevantes da consulta.
        """
        consulta_norm = self._normalizar_texto(
            consulta
        )

        palavras_ignoradas = {
            "o",
            "a",
            "os",
            "as",
            "um",
            "uma",
            "uns",
            "umas",
            "de",
            "do",
            "da",
            "dos",
            "das",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "para",
            "por",
            "com",
            "sobre",
            "que",
            "qual",
            "quais",
            "quem",
            "como",
            "quando",
            "onde",
            "voce",
            "lembra",
            "lembrar",
            "lembre",
            "memoria",
            "orion",
            "meu",
            "minha",
            "meus",
            "minhas",
            "sabe",
        }

        termos = []

        for palavra in consulta_norm.split():
            if (
                len(palavra) >= 3
                and palavra not in palavras_ignoradas
            ):
                termos.append(palavra)

        return termos

    def _extrair_corpo_memoria(self, texto):
        """
        Remove cabeçalho e metadados do Markdown antes de comparar o conteúdo
        real da memória.
        """
        linhas = str(texto or "").splitlines()
        corpo = []

        for linha in linhas:
            linha_strip = linha.strip()

            if linha_strip.startswith("#"):
                continue

            if linha_strip == "---":
                break

            if linha_strip.lower().startswith(
                ("criado pelo orion em ", "atualizado pelo orion em ")
            ):
                continue

            if linha_strip:
                corpo.append(linha_strip)

        return " ".join(corpo).strip()

    def _radical_palavra(self, palavra):
        """
        Faz uma redução simples de flexões comuns do português.
        Não é um stemmer linguístico completo; serve apenas para tornar a
        comparação de memórias menos literal.
        """
        palavra = self._normalizar_texto(palavra)

        if len(palavra) <= 3:
            return palavra

        sufixos = (
            "ariam",
            "eriam",
            "iriam",
            "ando",
            "endo",
            "indo",
            "ados",
            "adas",
            "idos",
            "idas",
            "aria",
            "eria",
            "iria",
            "aram",
            "eram",
            "iram",
            "ado",
            "ada",
            "ido",
            "ida",
            "ou",
            "ei",
            "am",
            "em",
            "ar",
            "er",
            "ir",
            "os",
            "as",
            "o",
            "a",
        )

        for sufixo in sufixos:
            if (
                palavra.endswith(sufixo)
                and len(palavra) - len(sufixo) >= 3
            ):
                return palavra[:-len(sufixo)]

        return palavra

    def _palavras_relevantes(self, texto):
        """
        Retorna palavras relevantes normalizadas para comparação entre
        memórias.
        """
        texto_norm = self._normalizar_texto(texto)

        ignoradas = {
            "o",
            "a",
            "os",
            "as",
            "um",
            "uma",
            "uns",
            "umas",
            "de",
            "do",
            "da",
            "dos",
            "das",
            "em",
            "no",
            "na",
            "nos",
            "nas",
            "para",
            "por",
            "com",
            "que",
            "e",
            "ao",
            "aos",
            "se",
            "ser",
            "foi",
            "vai",
            "usuario",
            "usuaria",
            "quer",
            "quero",
            "queria",
            "adicionar",
            "adiciona",
        }

        palavras = set()

        for palavra in texto_norm.split():
            if (
                len(palavra) >= 3
                and palavra not in ignoradas
            ):
                radical = self._radical_palavra(
                    palavra
                )

                if radical:
                    palavras.add(radical)

        return palavras

    def _similaridade_textual(self, texto_a, texto_b):
        """
        Calcula duas medidas de sobreposição e retorna a mais útil para
        detectar uma memória já contida em outra.
        """
        palavras_a = self._palavras_relevantes(texto_a)
        palavras_b = self._palavras_relevantes(texto_b)

        if not palavras_a or not palavras_b:
            return 0.0

        intersecao = palavras_a.intersection(
            palavras_b
        )

        cobertura = len(intersecao) / min(
            len(palavras_a),
            len(palavras_b),
        )

        uniao = palavras_a.union(
            palavras_b
        )

        jaccard = (
            len(intersecao) / len(uniao)
            if uniao
            else 0.0
        )

        return max(
            cobertura,
            jaccard,
        )

    # =========================================================
    # DUPLICIDADE
    # =========================================================

    def memoria_ja_existe(
        self,
        titulo,
        conteudo,
        categoria=None,
        limite_similaridade=0.75,
    ):
        """
        Verifica se já existe uma memória igual ou suficientemente parecida.

        O título igual sozinho NÃO basta para considerar duplicada: títulos
        podem ser truncados em 60 caracteres. O conteúdo também precisa ser
        compatível, evitando perda silenciosa de uma nova memória.
        """
        titulo = str(titulo or "").strip()
        conteudo = str(conteudo or "").strip()

        titulo_norm = self._normalizar_texto(
            titulo
        )

        conteudo_limpo = self._extrair_corpo_memoria(
            conteudo
        )

        if not conteudo_limpo:
            conteudo_limpo = conteudo

        conteudo_norm = self._normalizar_texto(
            conteudo_limpo
        )

        categoria_norm = str(
            categoria or ""
        ).strip().lower()

        if categoria_norm in self.pastas:
            pastas_busca = {
                categoria_norm: self.pastas[categoria_norm]
            }
        else:
            pastas_busca = self.pastas

        melhor_resultado = None

        for nome_categoria, pasta in pastas_busca.items():
            for arquivo in sorted(
                pasta.glob("*.md"),
                key=lambda item: item.name.lower(),
            ):
                texto_existente = self._ler_arquivo(
                    arquivo
                )

                if texto_existente is None:
                    continue

                titulo_existente = self._normalizar_texto(
                    arquivo.stem
                )

                corpo_existente = self._extrair_corpo_memoria(
                    texto_existente
                )

                conteudo_existente_norm = self._normalizar_texto(
                    corpo_existente
                )

                if (
                    conteudo_norm
                    and conteudo_existente_norm
                    and conteudo_norm == conteudo_existente_norm
                ):
                    return {
                        "titulo": arquivo.stem,
                        "categoria": nome_categoria,
                        "arquivo": str(arquivo),
                        "motivo": "conteudo_igual",
                        "similaridade": 1.0,
                    }

                if (
                    conteudo_norm
                    and conteudo_existente_norm
                    and (
                        conteudo_norm in conteudo_existente_norm
                        or conteudo_existente_norm in conteudo_norm
                    )
                ):
                    return {
                        "titulo": arquivo.stem,
                        "categoria": nome_categoria,
                        "arquivo": str(arquivo),
                        "motivo": "conteudo_contido",
                        "similaridade": 1.0,
                    }

                similaridade_titulo = self._similaridade_textual(
                    titulo,
                    arquivo.stem,
                )

                similaridade_conteudo = self._similaridade_textual(
                    conteudo_limpo,
                    corpo_existente,
                )

                similaridade = max(
                    similaridade_titulo,
                    similaridade_conteudo,
                )

                # Um título exatamente igual continua sendo um sinal forte,
                # mas não transforma automaticamente conteúdos diferentes em
                # duplicata.
                if (
                    titulo_norm
                    and titulo_norm == titulo_existente
                ):
                    similaridade = max(
                        similaridade,
                        similaridade_conteudo,
                    )

                if (
                    melhor_resultado is None
                    or similaridade
                    > melhor_resultado["similaridade"]
                ):
                    melhor_resultado = {
                        "titulo": arquivo.stem,
                        "categoria": nome_categoria,
                        "arquivo": str(arquivo),
                        "motivo": "conteudo_semelhante",
                        "similaridade": similaridade,
                    }

        if (
            melhor_resultado
            and melhor_resultado["similaridade"]
            >= float(limite_similaridade)
        ):
            return melhor_resultado

        return None

    # =========================================================
    # SALVAMENTO
    # =========================================================

    def salvar_nota(
        self,
        titulo,
        conteudo,
        categoria="notas",
    ):
        """
        Salva uma nota Markdown no Vault.

        Mantido compatível com o restante do Orion. Não sobrescreve
        silenciosamente outra nota: em colisão usa " (2)", " (3)", etc.
        """
        titulo = str(titulo or "").strip()
        conteudo = str(conteudo or "").strip()

        categoria = self._normalizar_categoria(
            categoria
        )

        pasta = self.pastas[categoria]

        titulo_exibicao = titulo or "Nota"
        titulo_seguro = self._titulo_seguro(
            titulo_exibicao,
            fallback="Nota",
        )

        arquivo = self._caminho_disponivel(
            pasta,
            titulo_seguro,
        )

        agora = datetime.now().strftime(
            "%d/%m/%Y %H:%M"
        )

        texto = (
            f"# {titulo_exibicao}\n\n"
            f"{conteudo}\n\n"
            "---\n"
            f"Criado pelo Orion em {agora}\n"
        )

        try:
            self._escrever_atomico(
                arquivo,
                texto,
            )
        except OSError as erro:
            print(
                f"Erro ao salvar memória {arquivo}:",
                erro,
            )
            return False

        print(
            f"Memória salva: {arquivo}"
        )

        return True

    def salvar_memoria_inteligente(
        self,
        titulo,
        conteudo,
        categoria="notas",
    ):
        """
        Salva uma memória somente se ainda não existir algo suficientemente
        semelhante.
        """
        titulo = str(titulo or "").strip()
        conteudo = str(conteudo or "").strip()

        categoria = self._normalizar_categoria(
            categoria
        )

        if not conteudo:
            return {
                "salva": False,
                "duplicada": False,
                "existente": None,
            }

        if not titulo:
            titulo = conteudo[:60].strip() or "Memória"

        existente = self.memoria_ja_existe(
            titulo=titulo,
            conteudo=conteudo,
            categoria=None,
        )

        if existente:
            print(
                "Memória automática ignorada: "
                "já existe algo semelhante."
            )

            print(
                f"Existente: {existente['titulo']} "
                f"| categoria={existente['categoria']} "
                f"| motivo={existente['motivo']} "
                f"| similaridade="
                f"{existente['similaridade']:.2f}"
            )

            return {
                "salva": False,
                "duplicada": True,
                "existente": existente,
            }

        salvo = self.salvar_nota(
            titulo=titulo,
            conteudo=conteudo,
            categoria=categoria,
        )

        return {
            "salva": bool(salvo),
            "duplicada": False,
            "existente": None,
        }

    # =========================================================
    # ATUALIZAÇÃO
    # =========================================================

    def atualizar_memoria(
        self,
        consulta,
        novo_conteudo,
        categoria=None,
    ):
        """
        Atualiza a memória mais relevante encontrada pela consulta.

        O novo arquivo é escrito antes de o antigo ser removido, diminuindo o
        risco de perda de memória caso a gravação falhe.
        """
        consulta = str(consulta or "").strip()
        novo_conteudo = str(novo_conteudo or "").strip()

        if not consulta or not novo_conteudo:
            return {
                "atualizada": False,
                "motivo": "dados_incompletos",
            }

        candidatos = self.buscar_memorias(
            consulta,
            limite=3,
        )

        categoria_norm = str(
            categoria or ""
        ).strip().lower()

        if categoria_norm in self.pastas:
            candidatos = [
                item
                for item in candidatos
                if item.get("categoria") == categoria_norm
            ]

        if not candidatos:
            return {
                "atualizada": False,
                "motivo": "nao_encontrada",
            }

        alvo = candidatos[0]
        arquivo_antigo = Path(
            alvo["arquivo"]
        )

        categoria_alvo = alvo["categoria"]

        titulo_novo = novo_conteudo[:60].strip()

        if len(novo_conteudo) > 60:
            titulo_novo = (
                titulo_novo.rstrip(" ,.;:-")
                + "..."
            )

        titulo_seguro = self._titulo_seguro(
            titulo_novo,
            fallback="Memória atualizada",
        )

        arquivo_novo = self._caminho_disponivel(
            self.pastas[categoria_alvo],
            titulo_seguro,
            ignorar=arquivo_antigo,
        )

        agora = datetime.now().strftime(
            "%d/%m/%Y %H:%M"
        )

        texto = (
            f"# {titulo_novo}\n\n"
            f"{novo_conteudo}\n\n"
            "---\n"
            f"Atualizado pelo Orion em {agora}\n"
        )

        try:
            self._escrever_atomico(
                arquivo_novo,
                texto,
            )
        except OSError as erro:
            print(
                f"Erro ao atualizar memória {arquivo_antigo}:",
                erro,
            )
            return {
                "atualizada": False,
                "motivo": "erro_gravacao",
            }

        try:
            mesmo_arquivo = (
                arquivo_antigo.exists()
                and arquivo_antigo.resolve()
                == arquivo_novo.resolve()
            )
        except OSError:
            mesmo_arquivo = (
                arquivo_antigo == arquivo_novo
            )

        if (
            arquivo_antigo.exists()
            and not mesmo_arquivo
        ):
            try:
                arquivo_antigo.unlink()
            except OSError as erro:
                # A atualização nova já foi gravada. Não apagamos a nova nota
                # só porque o arquivo antigo não pôde ser removido.
                print(
                    "Aviso: memória atualizada, mas não foi possível "
                    f"remover o arquivo antigo {arquivo_antigo}: {erro}"
                )

        print(
            "Memória atualizada: "
            f"{arquivo_antigo} -> {arquivo_novo}"
        )

        return {
            "atualizada": True,
            "categoria": categoria_alvo,
            "arquivo": str(arquivo_novo),
            "titulo_anterior": alvo["titulo"],
            "titulo_novo": titulo_novo,
        }

    # =========================================================
    # EXCLUSÃO
    # =========================================================

    def apagar_memoria(
        self,
        consulta,
        categoria=None,
    ):
        """
        Apaga a memória mais relevante encontrada pela consulta.
        """
        consulta = str(consulta or "").strip()

        if not consulta:
            return {
                "apagada": False,
                "motivo": "consulta_vazia",
            }

        candidatos = self.buscar_memorias(
            consulta,
            limite=3,
        )

        categoria_norm = str(
            categoria or ""
        ).strip().lower()

        if categoria_norm in self.pastas:
            candidatos = [
                item
                for item in candidatos
                if item.get("categoria") == categoria_norm
            ]

        if not candidatos:
            return {
                "apagada": False,
                "motivo": "nao_encontrada",
            }

        alvo = candidatos[0]
        arquivo = Path(
            alvo["arquivo"]
        )

        if not arquivo.exists():
            return {
                "apagada": False,
                "motivo": "arquivo_inexistente",
            }

        try:
            arquivo.unlink()
        except OSError as erro:
            print(
                f"Erro ao apagar memória {arquivo}:",
                erro,
            )
            return {
                "apagada": False,
                "motivo": "erro_exclusao",
            }

        print(
            f"Memória apagada: {arquivo}"
        )

        return {
            "apagada": True,
            "titulo": alvo["titulo"],
            "categoria": alvo["categoria"],
            "arquivo": str(arquivo),
        }

    # =========================================================
    # LEITURA E LISTAGEM
    # =========================================================

    def ler_nota(
        self,
        titulo,
        categoria="notas",
    ):
        """
        Procura uma nota pelo título.
        """
        categoria = self._normalizar_categoria(
            categoria
        )

        pasta = self.pastas[categoria]
        titulo_normalizado = self._normalizar_texto(
            titulo
        )

        if not titulo_normalizado:
            return None

        for arquivo in sorted(
            pasta.glob("*.md"),
            key=lambda item: item.name.lower(),
        ):
            if (
                titulo_normalizado
                in self._normalizar_texto(arquivo.stem)
            ):
                return self._ler_arquivo(
                    arquivo
                )

        return None

    def listar_notas(
        self,
        categoria="notas",
    ):
        """
        Retorna as notas existentes em uma categoria em ordem estável.
        """
        categoria = self._normalizar_categoria(
            categoria
        )

        pasta = self.pastas[categoria]

        return [
            arquivo.stem
            for arquivo in sorted(
                pasta.glob("*.md"),
                key=lambda item: item.name.lower(),
            )
        ]

    # =========================================================
    # BUSCA
    # =========================================================

    def _contar_termo(self, termo, palavras):
        """
        Conta apenas palavras inteiras.

        Isso evita, por exemplo, que a consulta "nome" ganhe pontos por
        encontrar apenas "sobrenome".
        """
        return sum(
            1
            for palavra in palavras
            if palavra == termo
        )

    def buscar_memorias(
        self,
        consulta,
        limite=5,
    ):
        """
        Busca memórias em todas as categorias.

        Retorna uma lista ordenada por relevância. A interface permanece
        compatível com brain.py e commands.py.
        """
        consulta = str(consulta or "").strip()

        try:
            limite = max(
                0,
                int(limite),
            )
        except (TypeError, ValueError):
            limite = 5

        if not consulta or limite == 0:
            return []

        consulta_norm = self._normalizar_texto(
            consulta
        )

        if (
            consulta_norm in {
                "mim",
                "sobre mim",
                "eu",
            }
            or consulta_norm.endswith("sobre mim")
        ):
            resultados_perfil = []

            for arquivo in self.pastas["perfil"].glob("*.md"):
                conteudo = self._ler_arquivo(
                    arquivo
                )

                if conteudo is None:
                    continue

                try:
                    mtime = arquivo.stat().st_mtime
                except OSError:
                    mtime = 0.0

                resultados_perfil.append({
                    "titulo": arquivo.stem,
                    "categoria": "perfil",
                    "conteudo": conteudo,
                    "score": 1,
                    "arquivo": str(arquivo),
                    "mtime": mtime,
                })

            resultados_perfil.sort(
                key=lambda item: (
                    item["mtime"],
                    item["titulo"].lower(),
                ),
                reverse=True,
            )

            for item in resultados_perfil:
                item.pop(
                    "mtime",
                    None,
                )

            return resultados_perfil[:limite]

        termos = self._extrair_termos_busca(
            consulta
        )

        if not termos:
            return []

        resultados = []

        for categoria, pasta in self.pastas.items():
            for arquivo in pasta.glob("*.md"):
                conteudo = self._ler_arquivo(
                    arquivo
                )

                if conteudo is None:
                    continue

                titulo_norm = self._normalizar_texto(
                    arquivo.stem
                )

                corpo = self._extrair_corpo_memoria(
                    conteudo
                )

                corpo_norm = self._normalizar_texto(
                    corpo
                )

                palavras_titulo = titulo_norm.split()
                palavras_corpo = corpo_norm.split()

                score = 0
                termos_encontrados = 0

                for termo in termos:
                    no_titulo = self._contar_termo(
                        termo,
                        palavras_titulo,
                    )

                    no_corpo = self._contar_termo(
                        termo,
                        palavras_corpo,
                    )

                    if no_titulo or no_corpo:
                        termos_encontrados += 1

                    # O título continua valendo mais que o conteúdo.
                    score += no_titulo * 3
                    score += no_corpo

                if score <= 0:
                    continue

                # Para consultas com mais de um termo, uma memória que bate
                # em apenas uma palavra genérica (por exemplo "favorito")
                # não deve competir com a memória que bate em "editor" e
                # "favorito" ao mesmo tempo.
                termos_unicos = set(termos)
                cobertura = (
                    termos_encontrados / len(termos_unicos)
                    if termos_unicos
                    else 0.0
                )

                if len(termos_unicos) >= 2 and cobertura < 0.60:
                    continue

                # Pequeno bônus quando vários termos diferentes da consulta
                # aparecem na mesma memória.
                if len(termos_unicos) > 1:
                    score += termos_encontrados

                resultados.append({
                    "titulo": arquivo.stem,
                    "categoria": categoria,
                    "conteudo": conteudo,
                    "score": score,
                    "cobertura": cobertura,
                    "arquivo": str(arquivo),
                })

        resultados.sort(
            key=lambda item: (
                item["score"],
                item["titulo"].lower(),
            ),
            reverse=True,
        )

        if not resultados:
            return []

        # Mantém somente resultados realmente competitivos com o melhor.
        # Isso evita enviar memórias fracas ao Qwen e deixá-lo escolher entre
        # fatos que não respondem à pergunta.
        melhor_score = resultados[0]["score"]
        score_minimo = max(1, int(melhor_score * 0.60))

        resultados_filtrados = [
            item
            for item in resultados
            if item["score"] >= score_minimo
        ]

        for item in resultados_filtrados:
            item.pop("cobertura", None)

        return resultados_filtrados[:limite]