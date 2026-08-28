# Orion

Assistente de inteligência artificial local desenvolvido em Python para Windows.

O Orion combina reconhecimento de voz, modelos de linguagem executados localmente, roteamento de intenções, memória e automações para permitir interação por voz com o computador e serviços integrados.

> Projeto em desenvolvimento e utilizado como ambiente de estudo e experimentação com IA local, automação e processamento de linguagem natural.

## Funcionalidades

- Reconhecimento de voz com Whisper
- Ativação manual ou por wake word
- Detecção de "Hey Jarvis" com OpenWakeWord
- Sessão de conversa após a ativação por voz
- Processamento local com Ollama
- Modelo principal Qwen 2.5 7B
- Modelo auxiliar Qwen 2.5 1.5B para roteamento
- Roteamento de intenções
- Memória e contexto de conversa
- Sistema de anotações
- Busca na web
- Integração com Spotify
- Abertura de aplicativos e páginas
- Controle de volume do Windows
- Respostas por voz
- Camada de segurança para bloquear ações potencialmente perigosas

## Arquitetura

O Orion utiliza diferentes componentes para separar reconhecimento de voz, interpretação, execução de comandos e geração de respostas.

Fluxo simplificado:

```text
Microfone
   ↓
Wake Word / Ativação manual
   ↓
Whisper (Speech-to-Text)
   ↓
Roteamento de intenção
   ↓
┌──────────────────────┬──────────────────────┐
│ Comando / Automação  │ Conversa / Pergunta  │
└──────────┬───────────┴──────────┬───────────┘
           ↓                      ↓
     Execução local          Ollama / Qwen
           ↓                      ↓
           └──────────┬───────────┘
                      ↓
                 Resposta
                      ↓
                    TTS
```

## Principais módulos

```text
main.py                   Inicialização e fluxo principal
audio_recorder.py         Captura de áudio
stt.py                    Transcrição com Whisper
wakeword_openwakeword.py  Detecção da palavra de ativação
intent_router.py          Roteamento inicial de intenções
ai_router.py              Roteamento semântico
brain.py                  Integração com o modelo de linguagem
commands.py               Execução de comandos
safety.py                 Validação de ações potencialmente perigosas
memory_manager.py         Gerenciamento da memória
memory_analyzer.py        Análise de informações para memória
notes.py                  Sistema de anotações
spotify_controller.py     Integração com Spotify
tv_controller.py          Integração experimental com TV
web_search.py             Busca na web
tts.py                    Conversão de texto em voz
config.py                 Configurações do projeto
```

## Modelos

O Orion utiliza atualmente:

```text
IA principal: qwen2.5:7b
Router:       qwen2.5:1.5b
Whisper:      medium
```

Os modelos Qwen são executados localmente através do Ollama.

## Requisitos

Antes de executar o projeto, é necessário ter:

- Python
- Ollama
- Microfone
- Modelos utilizados pelo Orion instalados localmente

Instale os modelos:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5:1.5b
```

## Instalação

Clone o repositório:

```powershell
git clone https://github.com/Keven-kantler/Orion.git
cd Orion
```

Crie um ambiente virtual:

```powershell
python -m venv venv
```

Ative o ambiente:

```powershell
.\venv\Scripts\Activate.ps1
```

Instale as dependências:

```powershell
pip install -r requirements.txt
```

## Configuração

O projeto utiliza variáveis de ambiente para manter configurações locais e credenciais fora do código.

Copie `.env.example` para `.env`:

```powershell
Copy-Item .env.example .env
```

Exemplo de configuração:

```env
ORION_HOME=

AUDIO_INPUT_DEVICE=

MODO_ATIVACAO=wakeword
WAKEWORD_ENGINE=openwakeword
OPENWAKEWORD_MODEL=hey_jarvis
OPENWAKEWORD_THRESHOLD=0.15

SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback

ROKU_TV_IP=
ROKU_TV_PORT=8060
```

O arquivo `.env` contém configurações locais e credenciais e não deve ser enviado ao repositório.

## Executando

Com o ambiente virtual ativado:

```powershell
python main.py
```

## Modos de ativação

### Wake word

No `.env`:

```env
MODO_ATIVACAO=wakeword
```

Diga:

```text
Hey Jarvis
```

Após detectar a palavra de ativação, o Orion começa a ouvir o comando.

A gravação é encerrada automaticamente após detectar silêncio.

Depois da primeira interação, uma sessão de conversa pode continuar sem exigir a wake word novamente a cada frase.

### Manual

Para utilizar o modo manual:

```env
MODO_ATIVACAO=manual
```

Nesse modo, a interação pode ser iniciada manualmente pelo teclado.

## Spotify

Para utilizar a integração com Spotify, configure suas próprias credenciais no arquivo `.env`:

```env
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

Na primeira autenticação, o navegador poderá ser aberto para autorizar o acesso à conta.

Os tokens de autenticação são armazenados localmente no arquivo `.spotify_cache`, que não deve ser enviado ao Git. O controlador utiliza esse arquivo local para o cache da autenticação.

Alguns recursos de reprodução através da API do Spotify podem exigir Spotify Premium.

## Exemplos de comandos

```text
Hey Jarvis

Abra o Spotify
Toque Back in Black
Pause a música
Qual música está tocando?

Abra o YouTube
Abra o Discord
Abra a calculadora

Aumente o volume
Diminua o volume

Pesquise sobre inteligência artificial

Crie uma anotação dizendo que hoje testei o Orion

Que horas são?
```

O Orion também pode responder perguntas gerais utilizando o modelo de linguagem local.

## Memória e contexto

O Orion possui um sistema experimental de memória que permite manter informações úteis entre interações.

Os dados de memória são armazenados localmente e não fazem parte do repositório público.

As pastas utilizadas para memória e anotações locais estão incluídas no `.gitignore`.

## Segurança

O projeto possui uma camada de segurança para impedir a execução automática de determinadas ações potencialmente perigosas.

Entre as ações bloqueadas estão operações como:

- desligar ou reiniciar o computador;
- excluir arquivos ou pastas;
- executar comandos arbitrários no terminal;
- executar scripts arbitrários;
- finalizar processos de maneira forçada.

Credenciais, tokens, memória, anotações e outros dados locais são mantidos fora do repositório através do `.gitignore` e de variáveis de ambiente.

## Limitações

O Orion ainda está em desenvolvimento.

Algumas funcionalidades podem depender de:

- qualidade do microfone;
- desempenho do hardware;
- disponibilidade dos modelos locais;
- conexão com a internet para serviços externos;
- APIs e serviços de terceiros.

O reconhecimento de voz e os modelos de linguagem são executados localmente, enquanto recursos como busca web e Spotify dependem de serviços externos.

## Status

Projeto experimental em desenvolvimento ativo.

O objetivo atual é explorar uma arquitetura modular para assistentes locais, combinando IA generativa, reconhecimento de voz, memória, roteamento de intenções e automação.

## Autor

Keven Kantler
