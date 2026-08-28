# Orion

Assistente de inteligÃªncia artificial local desenvolvido em Python para Windows.

O Orion combina reconhecimento de voz, modelos de linguagem executados localmente, roteamento de intenÃ§Ãµes, memÃ³ria e automaÃ§Ãµes para permitir interaÃ§Ã£o por voz com o computador e serviÃ§os integrados.

> Projeto em desenvolvimento e utilizado como ambiente de estudo e experimentaÃ§Ã£o com IA local, automaÃ§Ã£o e processamento de linguagem natural.

## Funcionalidades

- Reconhecimento de voz com Whisper
- AtivaÃ§Ã£o manual ou por wake word
- DetecÃ§Ã£o de "Hey Jarvis" com OpenWakeWord
- SessÃ£o de conversa apÃ³s a ativaÃ§Ã£o por voz
- Processamento local com Ollama
- Modelo principal Qwen 2.5 7B
- Modelo auxiliar Qwen 2.5 1.5B para roteamento
- Roteamento de intenÃ§Ãµes
- MemÃ³ria e contexto de conversa
- Sistema de anotaÃ§Ãµes
- Busca na web
- IntegraÃ§Ã£o com Spotify
- Abertura de aplicativos e pÃ¡ginas
- Controle de volume do Windows
- Respostas por voz
- Camada de seguranÃ§a para bloquear aÃ§Ãµes potencialmente perigosas

## Arquitetura

O Orion utiliza diferentes componentes para separar reconhecimento de voz, interpretaÃ§Ã£o, execuÃ§Ã£o de comandos e geraÃ§Ã£o de respostas.

Fluxo simplificado:

```text
Microfone
   â†“
Wake Word / AtivaÃ§Ã£o manual
   â†“
Whisper (Speech-to-Text)
   â†“
Roteamento de intenÃ§Ã£o
   â†“
â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”
â”‚ Comando / AutomaÃ§Ã£o  â”‚ Conversa / Pergunta  â”‚
â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”´â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
           â†“                      â†“
     ExecuÃ§Ã£o local          Ollama / Qwen
           â†“                      â†“
           â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”¬â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜
                      â†“
                 Resposta
                      â†“
                    TTS
```

## Principais mÃ³dulos

```text
main.py                   InicializaÃ§Ã£o e fluxo principal
audio_recorder.py         Captura de Ã¡udio
stt.py                    TranscriÃ§Ã£o com Whisper
wakeword_openwakeword.py  DetecÃ§Ã£o da palavra de ativaÃ§Ã£o
intent_router.py          Roteamento inicial de intenÃ§Ãµes
ai_router.py              Roteamento semÃ¢ntico
brain.py                  IntegraÃ§Ã£o com o modelo de linguagem
commands.py               ExecuÃ§Ã£o de comandos
safety.py                 ValidaÃ§Ã£o de aÃ§Ãµes potencialmente perigosas
memory_manager.py         Gerenciamento da memÃ³ria
memory_analyzer.py        AnÃ¡lise de informaÃ§Ãµes para memÃ³ria
notes.py                  Sistema de anotaÃ§Ãµes
spotify_controller.py     IntegraÃ§Ã£o com Spotify
tv_controller.py          IntegraÃ§Ã£o experimental com TV
web_search.py             Busca na web
tts.py                    ConversÃ£o de texto em voz
config.py                 ConfiguraÃ§Ãµes do projeto
```

## Modelos

O Orion utiliza atualmente:

```text
IA principal: qwen2.5:7b
Router:       qwen2.5:1.5b
Whisper:      medium
```

Os modelos Qwen sÃ£o executados localmente atravÃ©s do Ollama.

## Requisitos

Antes de executar o projeto, Ã© necessÃ¡rio ter:

- Python
- Ollama
- Microfone
- Modelos utilizados pelo Orion instalados localmente

Instale os modelos:

```powershell
ollama pull qwen2.5:7b
ollama pull qwen2.5:1.5b
```

## InstalaÃ§Ã£o

Clone o repositÃ³rio:

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

Instale as dependÃªncias:

```powershell
pip install -r requirements.txt
```

## ConfiguraÃ§Ã£o

O projeto utiliza variÃ¡veis de ambiente para manter configuraÃ§Ãµes locais e credenciais fora do cÃ³digo.

Copie `.env.example` para `.env`:

```powershell
Copy-Item .env.example .env
```

Exemplo de configuraÃ§Ã£o:

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

O arquivo `.env` contÃ©m configuraÃ§Ãµes locais e credenciais e nÃ£o deve ser enviado ao repositÃ³rio.

## Executando

Com o ambiente virtual ativado:

```powershell
python main.py
```

## Modos de ativaÃ§Ã£o

### Wake word

No `.env`:

```env
MODO_ATIVACAO=wakeword
```

Diga:

```text
Hey Jarvis
```

ApÃ³s detectar a palavra de ativaÃ§Ã£o, o Orion comeÃ§a a ouvir o comando.

A gravaÃ§Ã£o Ã© encerrada automaticamente apÃ³s detectar silÃªncio.

Depois da primeira interaÃ§Ã£o, uma sessÃ£o de conversa pode continuar sem exigir a wake word novamente a cada frase.

### Manual

Para utilizar o modo manual:

```env
MODO_ATIVACAO=manual
```

Nesse modo, a interaÃ§Ã£o pode ser iniciada manualmente pelo teclado.

## Spotify

Para utilizar a integraÃ§Ã£o com Spotify, configure suas prÃ³prias credenciais no arquivo `.env`:

```env
SPOTIFY_CLIENT_ID=
SPOTIFY_CLIENT_SECRET=
SPOTIFY_REDIRECT_URI=http://127.0.0.1:8888/callback
```

Na primeira autenticaÃ§Ã£o, o navegador poderÃ¡ ser aberto para autorizar o acesso Ã  conta.

Os tokens de autenticaÃ§Ã£o sÃ£o armazenados localmente no arquivo `.spotify_cache`, que nÃ£o deve ser enviado ao Git. O controlador utiliza esse arquivo local para o cache da autenticaÃ§Ã£o.

Alguns recursos de reproduÃ§Ã£o atravÃ©s da API do Spotify podem exigir Spotify Premium.

## Exemplos de comandos

```text
Hey Jarvis

Abra o Spotify
Toque Back in Black
Pause a mÃºsica
Qual mÃºsica estÃ¡ tocando?

Abra o YouTube
Abra o Discord
Abra a calculadora

Aumente o volume
Diminua o volume

Pesquise sobre inteligÃªncia artificial

Crie uma anotaÃ§Ã£o dizendo que hoje testei o Orion

Que horas sÃ£o?
```

O Orion tambÃ©m pode responder perguntas gerais utilizando o modelo de linguagem local.

## MemÃ³ria e contexto

O Orion possui um sistema experimental de memÃ³ria que permite manter informaÃ§Ãµes Ãºteis entre interaÃ§Ãµes.

Os dados de memÃ³ria sÃ£o armazenados localmente e nÃ£o fazem parte do repositÃ³rio pÃºblico.

As pastas utilizadas para memÃ³ria e anotaÃ§Ãµes locais estÃ£o incluÃ­das no `.gitignore`.

## SeguranÃ§a

O projeto possui uma camada de seguranÃ§a para impedir a execuÃ§Ã£o automÃ¡tica de determinadas aÃ§Ãµes potencialmente perigosas.

Entre as aÃ§Ãµes bloqueadas estÃ£o operaÃ§Ãµes como:

- desligar ou reiniciar o computador;
- excluir arquivos ou pastas;
- executar comandos arbitrÃ¡rios no terminal;
- executar scripts arbitrÃ¡rios;
- finalizar processos de maneira forÃ§ada.

Credenciais, tokens, memÃ³ria, anotaÃ§Ãµes e outros dados locais sÃ£o mantidos fora do repositÃ³rio atravÃ©s do `.gitignore` e de variÃ¡veis de ambiente.

## LimitaÃ§Ãµes

O Orion ainda estÃ¡ em desenvolvimento.

Algumas funcionalidades podem depender de:

- qualidade do microfone;
- desempenho do hardware;
- disponibilidade dos modelos locais;
- conexÃ£o com a internet para serviÃ§os externos;
- APIs e serviÃ§os de terceiros.

O reconhecimento de voz e os modelos de linguagem sÃ£o executados localmente, enquanto recursos como busca web e Spotify dependem de serviÃ§os externos.

## Status

Projeto experimental em desenvolvimento ativo.

O objetivo atual Ã© explorar uma arquitetura modular para assistentes locais, combinando IA generativa, reconhecimento de voz, memÃ³ria, roteamento de intenÃ§Ãµes e automaÃ§Ã£o.

## Autor

Keven Kantler

