from datetime import datetime
import re


SENSITIVE_KEYS = [
    "SMH_USER_TOKEN",
    "JAAuthCookie",
    "CANVAS_TOKEN",
    "user_token",
    "access_token",
    "Authorization",
]


def sanitize_message(message: str) -> str:
    sanitized = message
    for key in SENSITIVE_KEYS:
        sanitized = re.sub(
            rf"({re.escape(key)}\s*[=:]\s*)([^\s,;]+)",
            rf"\1***REDACTED***",
            sanitized,
            flags=re.IGNORECASE,
        )
        sanitized = re.sub(
            rf"([?&]{re.escape(key)}=)([^&\s]+)",
            rf"\1***REDACTED***",
            sanitized,
            flags=re.IGNORECASE,
        )

    sanitized = re.sub(
        r"(Bearer\s+)([^\s]+)",
        r"\1***REDACTED***",
        sanitized,
        flags=re.IGNORECASE,
    )
    return sanitized


def log(message: str) -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {sanitize_message(message)}")


def log_exception(context: str, exc: Exception) -> None:
    error_type = exc.__class__.__name__
    log(f"{context}: {error_type}")
