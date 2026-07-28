import asyncio
import json
import contextlib
from typing import Optional

import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from faster_whisper import WhisperModel

from app.utils.logger import setup_logger

router = APIRouter()
@router.get("/health")
async def stt_health():
    return {"status": "ok"}

logger = setup_logger(__name__)


class StreamingSession:
    def __init__(self, model: WhisperModel, sample_rate: int = 16000):
        self.model = model
        self.sample_rate = sample_rate
        self.buffer = np.zeros((0,), dtype=np.int16)
        self.lock = asyncio.Lock()
        self.closed = False

    async def append_pcm16(self, chunk: bytes):
        arr = np.frombuffer(chunk, dtype=np.int16)
        async with self.lock:
            self.buffer = np.concatenate([self.buffer, arr])
            logger.info(f"append_pcm16: chunk {len(chunk)} bytes, total buffer len {self.buffer.size}")

    async def transcribe_partial(self) -> Optional[str]:
        # Use a window (e.g., last ~15s) to keep latency reasonable
        window_samples = self.sample_rate * 15
        async with self.lock:
            if self.buffer.size == 0:
                return None
            buf = self.buffer[-window_samples:].astype(np.float32) / 32768.0
            logger.info(f"transcribe_partial: buf shape {buf.shape}, dtype {buf.dtype}, max: {buf.max()}, min: {buf.min()}")

        # faster-whisper expects float32 PCM at target sample rate
        # Beam size small for speed; vad_filter may help
        segments, _ = self.model.transcribe(
            buf, language="ru", beam_size=1, vad_filter=True, condition_on_previous_text=False
        )
        texts = [seg.text for seg in segments]
        return " ".join(texts).strip() if texts else None


_whisper_model: Optional[WhisperModel] = None


def get_model() -> WhisperModel:
    global _whisper_model
    if _whisper_model is None:
        # Use a small model for CPU; can be overridden by env in the future
        _whisper_model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info("Whisper model 'small' loaded (cpu, int8)")
    return _whisper_model


@router.websocket("/stream")
async def stt_stream(ws: WebSocket):
    await ws.accept()
    logger.info("STT websocket connected")
    model = get_model()
    session = StreamingSession(model=model, sample_rate=16000)

    # Background partial transcription loop
    async def partial_loop():
        try:
            while not session.closed:
                await asyncio.sleep(1.0)
                try:
                    text = await session.transcribe_partial()
                    logger.info(f"Partial transcription: {text}")
                    if text:
                        await ws.send_text(json.dumps({"type": "partial", "text": text}))
                except Exception as e:
                    logger.warning(f"Partial transcription error: {e}", exc_info=True)
        except asyncio.CancelledError:
            pass

    loop_task = asyncio.create_task(partial_loop())

    try:
        while True:
            msg = await ws.receive()
            logger.info(f"raw ws message: {msg}")
            # Bytes (audio)
            if "bytes" in msg and msg["bytes"] is not None:
                logger.info(f"Got PCM16 chunk: {len(msg['bytes'])} bytes")
                await session.append_pcm16(msg["bytes"])
            # Text (control)
            elif "text" in msg and msg["text"] is not None:
                try:
                    data = json.loads(msg["text"]) if msg["text"] else {}
                except Exception:
                    data = {}
                if data.get("event") == "stop":
                    final_text = await session.transcribe_partial()
                    await ws.send_text(json.dumps({"type": "final", "text": final_text or ""}))
                    break
            else:
                pass
    except WebSocketDisconnect:
        logger.info("STT websocket disconnected by client")
    except Exception as e:
        logger.error(f"STT websocket error: {e}", exc_info=True)
    finally:
        session.closed = True
        loop_task.cancel()
        with contextlib.suppress(Exception):
            await ws.close()
        logger.info("STT websocket closed")


