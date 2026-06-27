from __future__ import annotations

import re

SECRET_ENV_PATTERNS = (
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PRIVATE_KEY",
    "CREDENTIAL",
    "ACCESS_KEY",
    "SESSION",
)


def redact(text: str, env: dict[str, str]) -> str:
    redacted = text
    for key, value in env.items():
        if not value or len(value) < 4:
            continue
        if any(pattern in key for pattern in SECRET_ENV_PATTERNS):
            redacted = redacted.replace(value, f"<redacted:{key}>")
    redacted = re.sub(r"(Authorization=')Basic [^']+(')", r"\1Basic <redacted>\2", redacted)
    redacted = re.sub(
        r"(Authorization=')AWS4-HMAC-SHA256[^']+(')",
        r"\1<redacted:AWS4-HMAC-SHA256>\2",
        redacted,
    )
    redacted = re.sub(
        r"(x-amz-security-token=')[^']+(')",
        r"\1<redacted:x-amz-security-token>\2",
        redacted,
    )
    redacted = re.sub(
        r"(x-amz-security-token=')[^'\s]+",
        r"\1<redacted:x-amz-security-token>",
        redacted,
    )
    redacted = re.sub(r"(X-Amz-Credential=)[^&\s']+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(X-Amz-Signature=)[A-Fa-f0-9]+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(X-Amz-Security-Token=)[^&\s']+", r"\1<redacted>", redacted)
    redacted = re.sub(r"(x-amz-id-2=)[^,}\s]+", r"\1<redacted:x-amz-id-2>", redacted)
    redacted = re.sub(r"Bearer\s+[A-Za-z0-9._~+/=-]+", "Bearer <redacted>", redacted)
    redacted = re.sub(r"(client_secret=)[^&\s']+", r"\1<redacted>", redacted)
    return redacted


def first_error(output: str) -> str:
    for line in output.splitlines():
        if "Error:" in line or "Exception:" in line or "Catalog Error" in line:
            return line.strip()
    return output.splitlines()[-1].strip() if output.splitlines() else "unknown error"


def redacted_error(output: str, env: dict[str, str]) -> str:
    return redact(first_error(output), env)
