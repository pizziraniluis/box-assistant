"""
Teste de ciclo completo sem hardware de áudio:
  1. Manda um texto para o Piper (TTS) e salva como .wav válido
  2. Reenvia esse .wav para o Vosk (STT) e imprime a transcrição

Uso:
    python3 test_tts_stt.py "Ligar a luz da sala"
"""
import asyncio
import sys
import wave

from wyoming.client import AsyncTcpClient
from wyoming.tts import Synthesize
from wyoming.audio import AudioStart, AudioChunk, AudioStop
from wyoming.asr import Transcribe, Transcript


async def synthesize(text: str, out_path: str) -> None:
    rate, width, channels = 22050, 2, 1
    audio_bytes = b""

    async with AsyncTcpClient("localhost", 10200) as client:
        await client.write_event(Synthesize(text=text).event())
        while True:
            event = await client.read_event()
            if AudioStart.is_type(event.type):
                start = AudioStart.from_event(event)
                rate, width, channels = start.rate, start.width, start.channels
            elif AudioChunk.is_type(event.type):
                audio_bytes += AudioChunk.from_event(event).audio
            elif event.type == "audio-stop":
                break

    with wave.open(out_path, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(width)
        wf.setframerate(rate)
        wf.writeframes(audio_bytes)

    print(f"[Piper] WAV salvo em {out_path} ({len(audio_bytes)} bytes, {rate}Hz)")


async def transcribe(wav_path: str) -> str:
    with wave.open(wav_path, "rb") as wf:
        rate = wf.getframerate()
        width = wf.getsampwidth()
        channels = wf.getnchannels()
        audio_bytes = wf.readframes(wf.getnframes())

    async with AsyncTcpClient("localhost", 10300) as client:
        await client.write_event(Transcribe(language="pt").event())
        await client.write_event(AudioStart(rate=rate, width=width, channels=channels).event())

        # Envia em blocos de ~40ms
        chunk_size = int(rate * width * channels * 0.04)
        for i in range(0, len(audio_bytes), chunk_size):
            piece = audio_bytes[i:i + chunk_size]
            await client.write_event(
                AudioChunk(rate=rate, width=width, channels=channels, audio=piece).event()
            )
        await client.write_event(AudioStop().event())

        while True:
            event = await client.read_event()
            if event is None:
                return ""
            if Transcript.is_type(event.type):
                return Transcript.from_event(event).text or ""


async def main():
    text = sys.argv[1] if len(sys.argv) > 1 else "Ligar a luz da sala"
    wav_path = "teste_ciclo.wav"

    await synthesize(text, wav_path)
    transcript = await transcribe(wav_path)

    print(f"\nTexto original : {text}")
    print(f"Transcrição    : {transcript}")


if __name__ == "__main__":
    asyncio.run(main())