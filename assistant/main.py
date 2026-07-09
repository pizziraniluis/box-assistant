"""
Assistente de voz local, sem tela, para rodar em container Docker numa TV Box.

Fluxo:
  1. Escuta o microfone continuamente e envia áudio ao openWakeWord.
  2. Quando a wake word é detectada, grava o comando do usuário até detectar silêncio.
  3. Envia o áudio gravado ao Vosk (STT) e recebe o texto transcrito.
  4. Envia o texto ao llama.cpp (LLM) e recebe a resposta.
  5. Envia a resposta ao Piper (TTS) e toca o áudio de volta na caixinha de som.
"""

import asyncio
import logging

import numpy as np
import requests
import sounddevice as sd

from wyoming.audio import AudioChunk, AudioStart, AudioStop
from wyoming.asr import Transcribe, Transcript
from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize
from wyoming.wake import Detect, Detection

import config

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("assistant")


def audio_start_event() -> AudioStart:
    return AudioStart(
        rate=config.SAMPLE_RATE,
        width=config.SAMPLE_WIDTH,
        channels=config.CHANNELS,
    )


# ---------------------------------------------------------------------------
# 1. WAKE WORD
# ---------------------------------------------------------------------------

async def wait_for_wake_word() -> None:
    """Fica escutando o microfone e transmitindo áudio ao openWakeWord até
    detectar a wake word configurada."""
    log.info("Aguardando wake word (%s)...", config.WAKE_WORD_NAME)

    async with AsyncTcpClient(config.WAKEWORD_HOST, config.WAKEWORD_PORT) as client:
        await client.write_event(Detect(names=[config.WAKE_WORD_NAME]).event())
        await client.write_event(audio_start_event().event())

        stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=config.CHUNK_SAMPLES,
        )
        stream.start()
        try:
            while True:
                data, _ = stream.read(config.CHUNK_SAMPLES)
                chunk = AudioChunk(
                    rate=config.SAMPLE_RATE,
                    width=config.SAMPLE_WIDTH,
                    channels=config.CHANNELS,
                    audio=data.tobytes(),
                )
                await client.write_event(chunk.event())

                event = await client.read_event()
                if event is None:
                    continue
                if Detection.is_type(event.type):
                    detection = Detection.from_event(event)
                    log.info("Wake word detectada: %s", detection.name)
                    return
        finally:
            stream.stop()
            stream.close()
            await client.write_event(AudioStop().event())


# ---------------------------------------------------------------------------
# 2. GRAVA COMANDO + STT
# ---------------------------------------------------------------------------

def rms(data: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(data.astype(np.float32)))))


async def record_and_transcribe() -> str:
    """Grava o comando do usuário (até detectar silêncio) e envia ao Vosk,
    retornando o texto transcrito."""
    log.info("Gravando comando...")

    async with AsyncTcpClient(config.STT_HOST, config.STT_PORT) as client:
        await client.write_event(Transcribe(language="pt").event())
        await client.write_event(audio_start_event().event())

        stream = sd.InputStream(
            samplerate=config.SAMPLE_RATE,
            channels=config.CHANNELS,
            dtype="int16",
            blocksize=config.CHUNK_SAMPLES,
        )
        stream.start()

        silence_ms = 0
        total_ms = 0
        try:
            while True:
                data, _ = stream.read(config.CHUNK_SAMPLES)
                await client.write_event(
                    AudioChunk(
                        rate=config.SAMPLE_RATE,
                        width=config.SAMPLE_WIDTH,
                        channels=config.CHANNELS,
                        audio=data.tobytes(),
                    ).event()
                )

                total_ms += config.CHUNK_MS
                if rms(data.flatten()) < config.SILENCE_THRESHOLD:
                    silence_ms += config.CHUNK_MS
                else:
                    silence_ms = 0

                if silence_ms >= config.SILENCE_DURATION_MS:
                    log.info("Silêncio detectado, encerrando gravação.")
                    break
                if total_ms >= config.MAX_RECORD_SECONDS * 1000:
                    log.info("Tempo máximo de gravação atingido.")
                    break
        finally:
            stream.stop()
            stream.close()
            await client.write_event(AudioStop().event())

        # Lê eventos até receber a transcrição final
        while True:
            event = await client.read_event()
            if event is None:
                return ""
            if Transcript.is_type(event.type):
                transcript = Transcript.from_event(event)
                log.info("Transcrição: %s", transcript.text)
                return transcript.text or ""


# ---------------------------------------------------------------------------
# 3. LLM (llama.cpp, API compatível com OpenAI)
# ---------------------------------------------------------------------------

def ask_llm(user_text: str) -> str:
    log.info("Enviando para o LLM: %s", user_text)
    payload = {
        "model": "local",
        "messages": [
            {"role": "system", "content": config.LLM_SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ],
        "max_tokens": config.LLM_MAX_TOKENS,
        "temperature": 0.7,
    }
    try:
        resp = requests.post(config.LLM_URL, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        reply = data["choices"][0]["message"]["content"].strip()
        log.info("Resposta do LLM: %s", reply)
        return reply
    except Exception:
        log.exception("Erro ao consultar o LLM")
        return "Desculpa, tive um problema para pensar na resposta."


# ---------------------------------------------------------------------------
# 4. TTS (Piper) + PLAYBACK
# ---------------------------------------------------------------------------

async def speak(text: str) -> None:
    if not text:
        return
    log.info("Sintetizando fala...")

    async with AsyncTcpClient(config.TTS_HOST, config.TTS_PORT) as client:
        await client.write_event(Synthesize(text=text).event())

        audio_chunks = []
        rate = config.SAMPLE_RATE
        width = config.SAMPLE_WIDTH
        channels = config.CHANNELS

        while True:
            event = await client.read_event()
            if event is None:
                break
            if AudioStart.is_type(event.type):
                start = AudioStart.from_event(event)
                rate, width, channels = start.rate, start.width, start.channels
            elif AudioChunk.is_type(event.type):
                chunk = AudioChunk.from_event(event)
                audio_chunks.append(chunk.audio)
            elif AudioStop.is_type(event.type):
                break

        if not audio_chunks:
            log.warning("Nenhum áudio recebido do Piper.")
            return

        raw = b"".join(audio_chunks)
        audio_np = np.frombuffer(raw, dtype="int16")
        if channels > 1:
            audio_np = audio_np.reshape(-1, channels)

        sd.play(audio_np, samplerate=rate)
        sd.wait()


# ---------------------------------------------------------------------------
# LOOP PRINCIPAL
# ---------------------------------------------------------------------------

async def main() -> None:
    log.info("Assistente de voz iniciado.")
    while True:
        try:
            await wait_for_wake_word()
            user_text = await record_and_transcribe()

            if not user_text.strip():
                log.info("Nada reconhecido, voltando a escutar a wake word.")
                continue

            reply = ask_llm(user_text)
            await speak(reply)

        except Exception:
            log.exception("Erro no loop principal, tentando novamente em 3s...")
            await asyncio.sleep(3)


if __name__ == "__main__":
    asyncio.run(main())
