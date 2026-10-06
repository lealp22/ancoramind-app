"""Real synthetic audio/decoder tests; run in FFmpeg-enabled Linux container."""

import asyncio
import shutil
import subprocess
from unittest.mock import AsyncMock

import pytest

from src.agent.voice_inspector import FFmpegVoiceInspector
from src.domain.speech.policy import SpeechInputError

pytestmark = pytest.mark.skipif(
    not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg binaries required"
)


def generate(tmp_path, *, duration="1", codec="libopus", streams=1):
    output = tmp_path / "synthetic.ogg"
    command = ["ffmpeg", "-v", "error", "-y"]
    for _ in range(streams):
        command += ["-f", "lavfi", "-i", f"sine=frequency=440:duration={duration}"]
    for index in range(streams):
        command += ["-map", f"{index}:a"]
    command += ["-c:a", codec, str(output)]
    subprocess.run(command, check=True, capture_output=True, timeout=30)
    return output.read_bytes()


async def test_real_decode_and_temporary_cleanup(tmp_path):
    content = generate(tmp_path)
    root = tmp_path / "private"
    root.mkdir()
    result = await FFmpegVoiceInspector(temporary_root=str(root)).inspect(content)
    assert result.duration_seconds == 1
    assert result.content == content
    assert list(root.iterdir()) == []


@pytest.mark.parametrize(
    "kind", ["fake", "truncated", "checksum", "vorbis", "streams", "chained", "long"]
)
async def test_reject_real_invalid_audio_and_cleanup(tmp_path, kind):
    content = generate(
        tmp_path,
        duration="301" if kind == "long" else "1",
        codec="libvorbis" if kind == "vorbis" else "libopus",
        streams=2 if kind == "streams" else 1,
    )
    if kind == "fake":
        content = b"OggSfake"
    elif kind == "truncated":
        content = content[:-50]
    elif kind == "checksum":
        data = bytearray(content)
        data[-10] ^= 1
        content = bytes(data)
    elif kind == "chained":
        content += generate(tmp_path)
    root = tmp_path / "private"
    root.mkdir()
    with pytest.raises(SpeechInputError):
        await FFmpegVoiceInspector(temporary_root=str(root)).inspect(content)
    assert list(root.iterdir()) == []


@pytest.mark.parametrize("failure", ["cancel", "timeout"])
async def test_cancel_timeout_remove_temporary_input(tmp_path, failure):
    root = tmp_path / "private"
    root.mkdir()
    inspector = FFmpegVoiceInspector(temporary_root=str(root), timeout_seconds=0.05)

    async def slow(*args):
        assert list(root.iterdir())
        if failure == "cancel":
            raise asyncio.CancelledError()
        await asyncio.sleep(10)

    inspector._run = AsyncMock(side_effect=slow)
    with pytest.raises(asyncio.CancelledError if failure == "cancel" else SpeechInputError):
        await inspector.inspect(generate(tmp_path))
    assert not list(root.iterdir())


async def test_cancel_reaps_real_child():
    import sys

    inspector = FFmpegVoiceInspector()
    task = asyncio.create_task(
        inspector._run(sys.executable, ["-c", "import time;time.sleep(10)"], 10)
    )
    await asyncio.sleep(0.1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_subprocess_output_bound():
    import sys

    inspector = FFmpegVoiceInspector()
    with pytest.raises(SpeechInputError):
        await inspector._run(sys.executable, ["-c", "print('x'*100000)"], 10)
