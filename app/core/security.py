"""Password hashing and dynamic-command validation."""

import base64
import hashlib
import hmac
import secrets
import shlex
import string

from app.core.exceptions import ApiError


PASSWORD_ITERATIONS = 240_000
MAX_PASSWORD_ITERATIONS = 1_000_000
ALLOWED_EXECUTABLES = {
    "python",
    "python3",
    "g++",
    "gcc",
    "clang++",
    "node",
    "java",
    "go",
    "rustc",
}
FORBIDDEN_SHELL_TOKENS = {";", "&&", "||", "|", ">", "<", "`", "$", "\n", "\r"}


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        PASSWORD_ITERATIONS,
    )
    return "$".join(
        (
            "pbkdf2_sha256",
            str(PASSWORD_ITERATIONS),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations_text, salt_text, expected_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        iterations = int(iterations_text)
        if not 1 <= iterations <= MAX_PASSWORD_ITERATIONS:
            return False
        salt = base64.b64decode(salt_text, validate=True)
        expected = base64.b64decode(expected_text, validate=True)
        if len(salt) < 16 or len(expected) != hashlib.sha256().digest_size:
            return False
        actual = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            iterations,
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError, base64.binascii.Error):
        return False


def is_password_hash(encoded: str) -> bool:
    """Validate an imported hash without doing an expensive password check."""
    try:
        algorithm, iterations_text, salt_text, digest_text = encoded.split("$", 3)
        iterations = int(iterations_text)
        salt = base64.b64decode(salt_text, validate=True)
        digest = base64.b64decode(digest_text, validate=True)
    except (ValueError, TypeError, base64.binascii.Error):
        return False
    return (
        algorithm == "pbkdf2_sha256"
        and 1 <= iterations <= MAX_PASSWORD_ITERATIONS
        and len(salt) >= 16
        and len(digest) == hashlib.sha256().digest_size
    )


def validate_command_template(command: str, *, require_src: bool = False) -> None:
    if any(token in command for token in FORBIDDEN_SHELL_TOKENS):
        raise ApiError(400, "unsafe language command")
    try:
        parts = shlex.split(command)
    except ValueError as exc:
        raise ApiError(400, "invalid language command") from exc
    if not parts or parts[0] not in ALLOWED_EXECUTABLES and "{exe}" not in parts[0]:
        raise ApiError(400, "language executable is not allowed")
    if require_src and "{src}" not in command:
        raise ApiError(400, "language command must contain {src}")
    unknown = {
        field_name
        for _, field_name, _, _ in string.Formatter().parse(command)
        if field_name is not None and field_name not in {"src", "exe"}
    }
    if unknown:
        raise ApiError(400, "language command contains unsupported placeholders")
