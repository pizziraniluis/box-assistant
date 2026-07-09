# Assistente de Voz Local (Docker) — TV Box sem tela

Stack 100% local e offline, otimizada para dispositivos com pouca RAM (~1GB):

| Função       | Ferramenta                                |
|--------------|--------------------------------------------|
| Wake word    | openWakeWord (protocolo Wyoming)           |
| STT          | Vosk (modelo `small`, PT-BR)               |
| LLM          | llama.cpp + Qwen2.5-0.5B-Instruct (GGUF)   |
| TTS          | Piper (voz `pt_BR-edresson-low`)           |
| Orquestração | Script Python (`assistant/main.py`)        |
| Automação    | `Justfile` (subir, parar, logs, testes)    |

> **Status atual do projeto:** o assistente responde perguntas em conversa (LLM puro).
> Ele **ainda não aciona dispositivos IoT** (lâmpadas, tomadas, etc). Isso é uma fase
> futura — hoje o `LLM_SYSTEM_PROMPT` não dá ao modelo nenhuma ferramenta/function
> calling, só gera texto de resposta.

## Estrutura

```
box-assistant/
├── docker-compose.yml
├── Justfile                 # atalhos pra subir/parar/testar (veja `just` abaixo)
├── .gitignore
├── test_tts_stt.py          # testa o ciclo Piper -> Vosk sem precisar de microfone
├── models/                  # .gguf do LLM (não versionado, baixe com `just download-llm`)
├── piper/                   # voz do Piper, baixada automaticamente na 1ª execução
├── vosk-model/               # modelo Vosk PT-BR (baixe com `just download-vosk`)
├── vosk-sentences/           # pasta exigida pelo wyoming-vosk (fica vazia neste modo)
├── openwakeword/              # modelos customizados de wake word (opcional)
└── assistant/
    ├── Dockerfile
    ├── requirements.txt
    ├── config.py             # toda a configuração fica aqui
    └── main.py                # orquestrador: wake word -> STT -> LLM -> TTS
```

## Passo a passo

### 1. Baixar os modelos

```bash
just download-all
# ou separadamente:
just download-llm    # Qwen2.5-0.5B-Instruct Q4_K_M (~400MB)
just download-vosk   # vosk-model-small-pt-0.3 (~50MB)
```

### 2. Subir os serviços de back-end

```bash
just up
just ps
```

Na primeira execução, o Piper baixa automaticamente a voz `pt_BR-edresson-low` para dentro de `./piper`, e o Vosk carrega o modelo PT-BR — acompanhe com `just logs` até aparecer `Ready` em cada um.

### 3. Testar

```bash
just test-llm                              # testa só o LLM via curl
just test-cycle "Ligar a luz da sala"      # testa Piper -> Vosk (TTS gera áudio, Vosk transcreve de volta)
just test-ports                            # confere se as 4 portas estão respondendo
```

> Em ambientes sem hardware de áudio (Codespaces, servidores remotos), esse é o teste
> mais completo possível. O teste com microfone/caixa de som real só funciona rodando
> na própria TV Box (veja `up-full` abaixo).

### 4. Rodar o assistente completo (só em hardware com áudio, ex: a TV Box)

```bash
just up-full   # sobe também o serviço `assistant`, que precisa de /dev/snd
just logs-one assistant
```

Todos os comandos disponíveis: `just` (sem argumentos) lista tudo.

## Trocar o modelo do LLM por um maior

O modelo atual (Qwen2.5-0.5B) é bem pequeno — prioriza velocidade e baixo consumo de
RAM, mas erra mais em perguntas complexas. Se sua TV Box tiver RAM sobrando (2GB+),
vale subir de tamanho.

**1. Baixe o novo `.gguf`** (exemplos de modelos leves e bons em PT):

| Modelo | Tamanho aprox. (Q4_K_M) | RAM recomendada |
|---|---|---|
| Qwen2.5-0.5B-Instruct (atual) | ~400MB | 1GB |
| Qwen2.5-1.5B-Instruct | ~1GB | 2GB |
| Qwen2.5-3B-Instruct | ~2GB | 4GB |
| Llama-3.2-3B-Instruct | ~2GB | 4GB |

Exemplo trocando para o Qwen2.5-1.5B:
```bash
curl -L -o models/qwen2.5-1.5b-instruct-q4_k_m.gguf \
  "https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF/resolve/main/qwen2.5-1.5b-instruct-q4_k_m.gguf"
```

**2. Atualize o `command:` do serviço `llm` no `docker-compose.yml`**, trocando o
nome do arquivo em `-m`:
```yaml
  llm:
    command: >
      -m /models/qwen2.5-1.5b-instruct-q4_k_m.gguf
      -c 2048
      --host 0.0.0.0
      --port 8080
      -t 4
```

**3. Recrie o container:**
```bash
just recreate llm
just test-llm
```

Não precisa mudar nada no `assistant/main.py` — ele fala com o LLM via API compatível
com OpenAI, então qualquer `.gguf` compatível com llama.cpp funciona sem alteração de
código.

## Trocar a voz do TTS (Piper)

**1. Ouça as vozes disponíveis** no [demo interativo do Piper](https://rhasspy.github.io/piper-samples/demo.html)
(tem várias em `pt_BR` e `pt_PT`).

**2. Atualize o `command:` do serviço `piper`** no `docker-compose.yml` com o nome
da voz escolhida:
```yaml
  piper:
    command: --voice pt_BR-faber-medium --length-scale 1.0
```
- `pt_BR-edresson-low` (atual): mais leve, roda rápido, qualidade ok
- `pt_BR-faber-medium`: mais natural, um pouco mais pesada em CPU
- `length-scale`: controla a velocidade da fala (valores menores = mais rápido, ex: `0.9`)

**3. Recrie o container** — ele baixa a nova voz automaticamente:
```bash
just recreate piper
just logs-one piper   # espere aparecer "Ready" de novo
just test-cycle "Testando a nova voz"
```

## Mudar a personalidade / system prompt do assistente

Edite `assistant/config.py`:
```python
LLM_SYSTEM_PROMPT = os.getenv(
    "LLM_SYSTEM_PROMPT",
    "Você é um assistente de voz em português do Brasil. "
    "Responda de forma curta, direta e natural, em no máximo 2 frases.",
)
```

Esse texto é enviado como mensagem `system` em toda chamada ao LLM — é ele que define
tom, personalidade e limites de comportamento (ex: pedir respostas curtas, já que
respostas longas demoram mais pra sintetizar em voz e soam estranhas faladas).

Depois de editar, reconstrua o container do assistente:
```bash
just rebuild-assistant
```

Você também pode sobrescrever o system prompt sem editar código, via variável de
ambiente no `docker-compose.yml` (serviço `assistant`):
```yaml
    environment:
      - LLM_SYSTEM_PROMPT=Você é um assistente animado e brincalhão, mas sempre objetivo.
```

> **Lembrando:** nesta fase, o assistente só responde perguntas em texto/voz — o
> `system prompt` não dá acesso a nenhuma ferramenta de automação. Ele não liga
> luzes, não controla tomadas, não aciona nada. Um assistente que decide *executar
> ações* no mundo real (IoT) precisa de function calling / tool use configurado no
> LLM, mais um adaptador que converse com o protocolo dos seus dispositivos (ex:
> Home Assistant, Tasmota, Zigbee2MQTT) — isso é a próxima fase do projeto, ainda não
> implementada aqui.

## Periféricos de áudio para a TV Box

O container `assistant` acessa o áudio da própria TV Box via `/dev/snd`. Isso exige
hardware de entrada (microfone) e saída (alto-falante) reais conectados fisicamente —
a maioria das TV Boxes baratas não tem microfone embutido, e quando tem, costuma ser
de baixa qualidade ou mal suportado no Armbian/Linux.

**Saída de áudio (fala do assistente):**
- A saída P2/P1 (3.5mm) da maioria das TV Boxes já é boa o suficiente.
- Conecte uma caixinha de som — por cabo (mais simples e confiável) ou Bluetooth (mais
  prático, mas exige parear e configurar o Bluetooth como saída padrão do ALSA/PulseAudio).

**Entrada de áudio (escuta do usuário):**
- Evite depender do microfone interno da TV Box, se existir — costuma funcionar mal
  ou nem ser reconhecido pelo Armbian.
- Prefira um **headset com microfone** (fone antigo com fio, tipo os de celular) ou um
  **microfone USB simples** — ambos são baratos e muito mais confiáveis.

| Item | Recomendação | Por quê |
|---|---|---|
| Saída de som | Caixinha Bluetooth ou com cabo 3.5mm | A saída de áudio da TV Box geralmente já é boa |
| Microfone | Fone/headset antigo com mic, ou mic USB simples | Mais confiável que microfone interno (quando existe) |
| Combo recomendado | Headset com mic + caixinha Bluetooth | Barato, fácil de configurar, resultado consistente |

**Verificando os dispositivos no host (fora do container), antes de subir o `assistant`:**
```bash
# lista dispositivos de captura (microfones)
arecord -l

# lista dispositivos de reprodução (saída de som)
aplay -l

# testa gravação de 5 segundos
arecord -d 5 -f cd teste.wav

# testa reprodução
aplay teste.wav
```
Se `arecord -l` não mostrar seu headset/mic USB, o problema é de driver/permissão no
host — resolva isso antes de subir o container, porque o Docker só repassa o que já
está funcionando em `/dev/snd`.

Se sua TV Box tiver mais de uma placa de som (ex: saída HDMI + P2), defina o dispositivo
padrão certo no host (`alsamixer` ou editando `~/.asoundrc`) antes de subir o
`docker compose up -d assistant`, senão o script pode tentar gravar/tocar no
dispositivo errado.

## Ajustes importantes já cobertos no projeto

- **Wake word**: o openWakeWord vem com alguns modelos prontos (`hey_jarvis`, `alexa`,
  `hey_mycroft`, etc). Para uma wake word customizada tipo "Ei Box", treine um modelo
  próprio (veja a [documentação do openWakeWord](https://github.com/dscripka/openWakeWord#training-new-models))
  e coloque o `.tflite`/`.onnx` em `./openwakeword`, ajustando `WAKE_WORD_NAME` e o
  `command:` do serviço no compose.
- **Threshold de silêncio** (`SILENCE_THRESHOLD`/`SILENCE_DURATION_MS` em `config.py`):
  depende do ruído ambiente e da sensibilidade do microfone escolhido. Ajuste depois
  de testar na prática.
- **RAM**: com Qwen2.5-0.5B em Q4_K_M (~400MB) + Vosk small (~50MB) + Piper (~60MB) +
  openWakeWord (~30MB), a stack inteira roda folgada em 1GB.

## Comandos rápidos (Justfile)

```bash
just              # lista todos os comandos
just up           # sobe os serviços de back-end (sem áudio)
just up-full      # sobe tudo, incluindo o assistant (precisa de /dev/snd)
just ps           # status dos containers
just logs         # logs de tudo, em tempo real
just logs-one <serviço>   # logs de um serviço específico
just restart <serviço>    # reinicia um serviço
just recreate <serviço>   # recria do zero (após mudar o compose)
just rebuild-assistant    # reconstrói o container assistant (após editar main.py/config.py)
just test-llm     # testa o LLM via curl
just test-cycle "texto"   # testa Piper -> Vosk
just test-ports   # confere se as portas estão de pé
just stop         # para tudo sem remover
just down         # remove containers e redes
just clean        # down -v (limpa volumes anônimos, mantém modelos em disco)
```