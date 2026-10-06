"""Offline pinned-image STT smoke: synthetic bytes, local upstream, no secrets.

Run in the Gateway image with --network none. Tests the real proxy HTTP endpoint,
not a mocked application client. The OpenAI-compatible route still points to
OpenRouter in deployment; this does not authorize publishing a production alias.
"""

import io
import json
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def main() -> None:
    seen: list[bytes] = []

    class Upstream(BaseHTTPRequestHandler):
        def do_POST(self) -> None:
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append(body)
            assert self.path == "/api/v1/audio/transcriptions"
            assert b"openai/whisper-large-v3" in body
            assert b"synthetic-audio-canary" in body
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"text": "synthetic transcript"}).encode())

        def log_message(self, *args: object) -> None:
            pass

    upstream = ThreadingHTTPServer(("127.0.0.1", 18081), Upstream)
    thread = threading.Thread(target=upstream.serve_forever, daemon=True)
    thread.start()
    with tempfile.TemporaryDirectory() as directory:
        config = Path(directory) / "config.yaml"
        config.write_text("""model_list:
  - model_name: stt-compat-r1
    litellm_params:
      model: openai/openai/whisper-large-v3
      api_base: http://127.0.0.1:18081/api/v1
      api_key: synthetic-not-a-secret
router_settings:
  num_retries: 0
litellm_settings:
  num_retries: 0
""")
        with tempfile.TemporaryFile() as output:
            process = subprocess.Popen(
                ["litellm", "--config", str(config), "--port", "18080"],
                stdout=output,
                stderr=output,
            )
            try:
                for _ in range(120):
                    try:
                        urllib.request.urlopen(
                            "http://127.0.0.1:18080/health/liveliness", timeout=1
                        )
                        break
                    except (OSError, urllib.error.URLError):
                        if process.poll() is not None:
                            raise RuntimeError("proxy_start_failed") from None
                        time.sleep(0.5)
                else:
                    raise RuntimeError("proxy_start_timeout")
                boundary = "ancora-synthetic-boundary"
                body = io.BytesIO()
                for name, value in (("model", "stt-compat-r1"), ("response_format", "json")):
                    body.write(
                        (
                            f"--{boundary}\r\nContent-Disposition: form-data; "
                            f'name="{name}"\r\n\r\n{value}\r\n'
                        ).encode()
                    )
                body.write(
                    (
                        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
                        'filename="voice.ogg"\r\nContent-Type: audio/ogg\r\n\r\n'
                        f"synthetic-audio-canary\r\n--{boundary}--\r\n"
                    ).encode()
                )
                request = urllib.request.Request(
                    "http://127.0.0.1:18080/v1/audio/transcriptions",
                    data=body.getvalue(),
                    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                )
                with urllib.request.urlopen(request, timeout=30) as response:
                    assert json.load(response)["text"] == "synthetic transcript"
                assert len(seen) == 1, "retry_or_fallback_detected"
                print(
                    "PASS proxy STT: alias resolved, exact model/file forwarded, one upstream call"
                )
            finally:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
                upstream.shutdown()


if __name__ == "__main__":
    main()
