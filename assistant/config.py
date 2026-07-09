import os

# --- Serviços Wyoming ---
WAKEWORD_HOST = os.getenv("WAKEWORD_HOST", "openwakeword")
WAKEWORD_PORT = int(os.getenv("WAKEWORD_PORT", "10400"))
WAKE_WORD_NAME = os.getenv("WAKE_WORD_NAME", "hey_jarvis")

STT_HOST = os.getenv("STT_HOST", "vosk")
STT_PORT = int(os.getenv("STT_PORT", "10300"))

TTS_HOST = os.getenv("TTS_HOST", "piper")
TTS_PORT = int(os.getenv("TTS_PORT", "10200"))

# --- LLM (llama.cpp, API compatível com OpenAI) ---
LLM_URL = os.getenv("LLM_URL", "http://llm:8080/v1/chat/completions")
LLM_SYSTEM_PROMPT = os.getenv(
    "LLM_SYSTEM_PROMPT",
    "Você é um assistente de voz em português do Brasil. "
    "Responda de forma curta, direta e natural, em no máximo 2 frases.",
)
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "150"))

# --- Áudio ---
SAMPLE_RATE = 16000          # taxa esperada pelos serviços Wyoming
CHANNELS = 1
SAMPLE_WIDTH = 2              # 16-bit PCM
CHUNK_MS = 40                 # tamanho de cada bloco de áudio capturado
CHUNK_SAMPLES = int(SAMPLE_RATE * CHUNK_MS / 1000)

# Silêncio: se o volume ficar abaixo do limiar por esse tempo, encerramos a gravação
SILENCE_THRESHOLD = int(os.getenv("SILENCE_THRESHOLD", "300"))   # amplitude RMS
SILENCE_DURATION_MS = int(os.getenv("SILENCE_DURATION_MS", "1200"))
MAX_RECORD_SECONDS = int(os.getenv("MAX_RECORD_SECONDS", "12"))
