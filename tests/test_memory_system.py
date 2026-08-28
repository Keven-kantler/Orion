import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ai_router import AIRouter
from brain import OrionBrain
import commands
from memory_analyzer import MemoryAnalyzer
from memory_manager import MemoryManager
from web_search import precisa_pesquisar


class MemorySystemTests(unittest.TestCase):
    def test_memory_analyzer_detects_durable_preference(self):
        resultado = MemoryAnalyzer().analisar(
            "meu editor favorito é VS Code"
        )

        self.assertTrue(resultado["salvar"])
        self.assertEqual(resultado["categoria"], "perfil")
        self.assertIn("VS Code", resultado["conteudo"])

    def test_memory_analyzer_does_not_save_questions(self):
        resultado = MemoryAnalyzer().analisar(
            "qual é meu editor favorito?"
        )

        self.assertFalse(resultado["salvar"])

    def test_router_detects_personal_memory_queries(self):
        router = AIRouter()

        casos = (
            "qual é meu editor favorito?",
            "você lembra qual é o meu nome?",
            "qual o nome da minha namorada?",
        )

        for texto in casos:
            with self.subTest(texto=texto):
                resultado = router.interpretar(texto)
                self.assertEqual(
                    resultado["intent"],
                    "consultar_memoria",
                )

    def test_router_does_not_treat_public_question_as_memory(self):
        resultado = AIRouter().interpretar("quem é Tony Stark?")

        self.assertNotEqual(
            resultado["intent"],
            "consultar_memoria",
        )

    def test_router_detects_update_delete_and_save_variants(self):
        router = AIRouter()

        self.assertEqual(
            router.interpretar(
                "corrija meu editor favorito para Cursor"
            )["intent"],
            "atualizar_memoria",
        )

        self.assertEqual(
            router.interpretar(
                "esquece meu editor favorito"
            )["intent"],
            "apagar_memoria",
        )

        self.assertEqual(
            router.interpretar(
                "lembre do nome da minha namorada, Evelyn"
            )["intent"],
            "salvar_memoria",
        )

    def test_personal_memory_question_does_not_trigger_web_search(self):
        self.assertFalse(
            precisa_pesquisar("qual é meu editor favorito?")
        )

    def test_memory_manager_uses_temp_vault_and_finds_current_name(self):
        with tempfile.TemporaryDirectory() as pasta:
            manager = MemoryManager(pasta_memoria=pasta)
            manager.salvar_memoria_inteligente(
                titulo="meu nome é Kevin",
                conteudo="meu nome é Kevin",
                categoria="perfil",
            )

            resultados = manager.buscar_memorias(
                "qual é meu nome?"
            )

            self.assertTrue(resultados)
            self.assertIn(
                "Kevin",
                resultados[0]["conteudo"],
            )
            self.assertTrue(Path(resultados[0]["arquivo"]).exists())

    def test_memory_manager_about_me_lists_profile_memories(self):
        with tempfile.TemporaryDirectory() as pasta:
            manager = MemoryManager(pasta_memoria=pasta)
            manager.salvar_memoria_inteligente(
                titulo="meu nome é Kevin",
                conteudo="meu nome é Kevin",
                categoria="perfil",
            )

            resultados = manager.buscar_memorias(
                "o que você lembra sobre mim?"
            )

            self.assertTrue(resultados)
            self.assertEqual(resultados[0]["categoria"], "perfil")
            self.assertIn("Kevin", resultados[0]["conteudo"])

    def test_brain_memory_context_ignores_conflicting_short_history(self):
        brain = OrionBrain()
        brain.historico = [
            {
                "role": "user",
                "content": "meu nome é Bonny",
            },
            {
                "role": "assistant",
                "content": "Seu nome é Bonny.",
            },
        ]

        chamadas = {}

        def fake_chat(**kwargs):
            chamadas["messages"] = kwargs["messages"]
            return {
                "message": {
                    "content": "Seu nome é Kevin.",
                }
            }

        with patch("brain.ollama.chat", side_effect=fake_chat):
            resposta = brain.perguntar_ia(
                "qual é meu nome?",
                contexto_memoria="meu nome é Kevin",
            )

        mensagens = chamadas["messages"]
        texto_mensagens = "\n".join(
            mensagem["content"]
            for mensagem in mensagens
        )

        self.assertEqual(resposta, "Seu nome é Kevin.")
        self.assertIn("Kevin", texto_mensagens)
        self.assertNotIn("Bonny", texto_mensagens)

    def test_memory_update_replaces_old_value_in_temp_vault(self):
        with tempfile.TemporaryDirectory() as pasta:
            manager = MemoryManager(pasta_memoria=pasta)
            manager.salvar_memoria_inteligente(
                titulo="meu editor favorito é VS Code",
                conteudo="meu editor favorito é VS Code",
                categoria="perfil",
            )

            resultado = manager.atualizar_memoria(
                consulta="meu editor favorito",
                novo_conteudo="meu editor favorito e Cursor",
            )

            self.assertTrue(resultado["atualizada"])
            memorias = manager.buscar_memorias(
                "qual é meu editor favorito?"
            )
            conteudo = "\n".join(
                memoria["conteudo"]
                for memoria in memorias
            )

            self.assertIn("Cursor", conteudo)
            self.assertNotIn("VS Code", conteudo)

    def test_memory_delete_removes_value_from_temp_vault(self):
        with tempfile.TemporaryDirectory() as pasta:
            manager = MemoryManager(pasta_memoria=pasta)
            manager.salvar_memoria_inteligente(
                titulo="meu editor favorito é VS Code",
                conteudo="meu editor favorito é VS Code",
                categoria="perfil",
            )

            resultado = manager.apagar_memoria(
                consulta="meu editor favorito",
            )

            self.assertTrue(resultado["apagada"])
            self.assertEqual(
                manager.buscar_memorias(
                    "qual é meu editor favorito?"
                ),
                [],
            )

    def test_command_update_clears_short_history(self):
        with tempfile.TemporaryDirectory() as pasta:
            manager = MemoryManager(pasta_memoria=pasta)
            manager.salvar_memoria_inteligente(
                titulo="meu editor favorito é VS Code",
                conteudo="meu editor favorito é VS Code",
                categoria="perfil",
            )

            brain = OrionBrain()
            brain.historico = [
                {
                    "role": "assistant",
                    "content": "Seu editor favorito é VS Code.",
                }
            ]

            with patch.object(commands, "memory_manager", manager):
                resposta = commands.processar_texto_usuario(
                    "corrija meu editor favorito para Cursor",
                    brain,
                    spotify=None,
                )

            self.assertEqual(resposta, "Corrigi essa memória.")
            self.assertEqual(brain.historico, [])

    def test_command_delete_clears_short_history(self):
        with tempfile.TemporaryDirectory() as pasta:
            manager = MemoryManager(pasta_memoria=pasta)
            manager.salvar_memoria_inteligente(
                titulo="meu editor favorito é VS Code",
                conteudo="meu editor favorito é VS Code",
                categoria="perfil",
            )

            brain = OrionBrain()
            brain.historico = [
                {
                    "role": "assistant",
                    "content": "Seu editor favorito é VS Code.",
                }
            ]

            with patch.object(commands, "memory_manager", manager):
                resposta = commands.processar_texto_usuario(
                    "esquece meu editor favorito",
                    brain,
                    spotify=None,
                )

            self.assertEqual(resposta, "Esqueci essa informação.")
            self.assertEqual(brain.historico, [])


if __name__ == "__main__":
    unittest.main()
