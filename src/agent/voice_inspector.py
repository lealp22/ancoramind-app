"""Local bounded OGG/Opus inspection and full decode; no audio retention."""

import asyncio
import json
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Literal

from src.domain.speech.models import MAX_VOICE_BYTES, InspectedVoiceAudio
from src.domain.speech.policy import SpeechInputError

FailureCode = Literal["voice_empty_or_invalid", "voice_probe_failed", "voice_decode_failed"]


class FFmpegVoiceInspector:
    """Probe one local file then count decoded mono PCM samples, not metadata time.

    Temporary directories are private and removed on success, error and
    cancellation. Subprocesses have no shell/network, bounded output and deadline.
    This is not an OS sandbox: container memory/CPU limits remain operational gates.
    """

    def __init__(
        self,
        *,
        ffprobe: str = "ffprobe",
        ffmpeg: str = "ffmpeg",
        temporary_root: str | None = None,
        timeout_seconds: float = 15,
    ):
        self._probe = shutil.which(ffprobe)
        self._decoder = shutil.which(ffmpeg)
        if self._probe is None or self._decoder is None:
            raise ValueError("voice_inspector_binaries_unavailable")
        self._root = temporary_root
        self._timeout = timeout_seconds

    async def _run(
        self,
        executable: str,
        args: list[str],
        limit: int,
        failure: FailureCode = "voice_empty_or_invalid",
    ) -> bytes:
        process = await asyncio.create_subprocess_exec(
            executable,
            *args,
            stdin=asyncio.subprocess.DEVNULL,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        assert process.stdout is not None and process.stderr is not None

        async def read_bounded(stream: asyncio.StreamReader, maximum: int) -> bytes:
            result = bytearray()
            while chunk := await stream.read(16384):
                result.extend(chunk)
                if len(result) > maximum:
                    raise SpeechInputError(failure)
            return bytes(result)

        tasks = [
            asyncio.create_task(read_bounded(process.stdout, limit)),
            asyncio.create_task(read_bounded(process.stderr, 16384)),
        ]
        try:
            output, errors = await asyncio.gather(*tasks)
            code = await process.wait()
            if code or errors:
                raise SpeechInputError(failure)
            return output
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def inspect(self, content: bytes) -> InspectedVoiceAudio:
        if not content or not content.startswith(b"OggS"):
            raise SpeechInputError("voice_empty_or_invalid")
        if len(content) > MAX_VOICE_BYTES:
            raise SpeechInputError("voice_too_large")
        # FFmpeg may silently decode an incomplete final page. Require a complete,
        # single logical OGG stream with BOS/EOS before invoking native binaries.
        offset = 0
        serial = None
        sequence = 0
        ended = False
        while offset < len(content):
            if ended or content[offset : offset + 4] != b"OggS" or len(content) - offset < 27:
                raise SpeechInputError("voice_ogg_structure_invalid")
            header = content[offset : offset + 27]
            flags = header[5]
            current_serial = header[14:18]
            current_sequence = int.from_bytes(header[18:22], "little")
            count = header[26]
            table_end = offset + 27 + count
            if (
                header[4] != 0
                or flags & ~7
                or table_end > len(content)
                or current_sequence != sequence
                or (sequence == 0 and not flags & 2)
                or (sequence > 0 and flags & 2)
                or (serial is not None and serial != current_serial)
            ):
                raise SpeechInputError("voice_ogg_structure_invalid")
            end = table_end + sum(content[offset + 27 : table_end])
            if end > len(content):
                raise SpeechInputError("voice_ogg_structure_invalid")
            serial = current_serial
            sequence += 1
            ended = bool(flags & 4)
            offset = end
        # Telegram voice notes may omit the EOS flag on the last page, so EOS is
        # not required. Truncation is still caught: every page must be complete
        # (no partial trailing page), FFmpeg decodes with -xerror/explode, and the
        # decoded duration must match the probed one.
        # A generated path only. No caller filename, URL, protocol or output path.
        with tempfile.TemporaryDirectory(prefix="ancora-voice-", dir=self._root) as directory:
            path = Path(directory) / "input.ogg"
            path.write_bytes(content)
            try:
                async with asyncio.timeout(self._timeout):
                    assert self._probe is not None and self._decoder is not None
                    probe = await self._run(
                        self._probe,
                        [
                            "-v",
                            "error",
                            "-max_alloc",
                            "16777216",
                            "-protocol_whitelist",
                            "file",
                            "-f",
                            "ogg",
                            "-show_entries",
                            "format=format_name,duration:stream=codec_type,codec_name,channels,sample_rate",
                            "-of",
                            "json",
                            str(path),
                        ],
                        16384,
                        "voice_probe_failed",
                    )
                    metadata = json.loads(probe)
                    streams = metadata["streams"]
                    if (
                        len(streams) != 1
                        or streams[0]["codec_type"] != "audio"
                        or streams[0]["codec_name"] != "opus"
                    ):
                        raise SpeechInputError("voice_format_not_allowed")
                    duration = Decimal(metadata["format"]["duration"])
                    if not duration.is_finite() or duration <= 0:
                        raise SpeechInputError("voice_probe_failed")
                    if duration > Decimal("300.1"):
                        raise SpeechInputError("voice_duration_exceeded")
                    pcm = await self._run(
                        self._decoder,
                        [
                            "-nostdin",
                            "-v",
                            "error",
                            "-xerror",
                            "-err_detect",
                            "explode",
                            "-max_alloc",
                            "16777216",
                            "-threads",
                            "1",
                            "-protocol_whitelist",
                            "file,pipe",
                            "-f",
                            "ogg",
                            "-i",
                            str(path),
                            "-map",
                            "0:a:0",
                            "-vn",
                            "-sn",
                            "-dn",
                            "-threads",
                            "1",
                            "-ac",
                            "1",
                            "-ar",
                            "16000",
                            "-t",
                            "300.1",
                            "-f",
                            "s16le",
                            "pipe:1",
                        ],
                        9603200,
                        "voice_decode_failed",
                    )
                    actual = Decimal(len(pcm)) / Decimal(32000)
                    if actual > 300:
                        raise SpeechInputError("voice_duration_exceeded")
                    if not pcm:
                        raise SpeechInputError("voice_decode_failed")
                    if abs(duration - actual) > Decimal("0.1"):
                        raise SpeechInputError("voice_duration_mismatch")
                    return InspectedVoiceAudio(
                        content=content,
                        mime_type="audio/ogg",
                        codec="opus",
                        duration_seconds=actual,
                    )
            except SpeechInputError:
                raise
            except (ValueError, KeyError, TypeError, ArithmeticError):
                raise SpeechInputError("voice_probe_failed") from None
            except (TimeoutError, OSError):
                raise SpeechInputError("voice_empty_or_invalid") from None
