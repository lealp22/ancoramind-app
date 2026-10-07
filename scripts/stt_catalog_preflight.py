"""Public catalog only: no credentials, audio, paid inference or remote writes."""

import json
from datetime import UTC, datetime

import httpx


def main() -> None:
    with httpx.Client(timeout=30, follow_redirects=False) as client:
        response = client.get(
            "https://openrouter.ai/api/v1/models",
            params={"output_modalities": "transcription"},
        )
        response.raise_for_status()
        models = response.json()["data"]
    print(
        json.dumps(
            {
                "checked_at": datetime.now(UTC).isoformat(),
                "inference_performed": False,
                "models": [
                    {
                        "id": model["id"],
                        "pricing_raw": model.get("pricing"),
                        "architecture": model.get("architecture"),
                    }
                    for model in models
                    if "whisper" in model["id"]
                ],
                "privacy_status": "blocked_pending_explicit_review",
                "billing_minimum_and_rounding": "unverified",
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
