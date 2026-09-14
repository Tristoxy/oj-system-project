"""Password hashing and dynamic-command validation."""

import base64
import hashlib
import hmac
import secrets
import shlex
import string

from app.core.exceptions import ApiError

# 密码安全、动态编程语言命令安全
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

# 把明文密码转化为安全哈希
# 为每个密码生成随机盐，并用 PBKDF2-SHA256 派生可持久化的哈希字符串。
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


# 解析已存哈希、重新计算候选密码摘要，并以常量时间方式比较结果。
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


# 只检查导入密码哈希的算法、迭代次数、Base64 和长度是否合法，不执行昂贵验证。
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


# 限制动态语言命令的可执行程序、占位符和 Shell 元字符，阻止命令注入。
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
    try:
        parsed = list(string.Formatter().parse(command))
    except ValueError as exc:
        raise ApiError(400, "invalid language command template") from exc
    fields = [field_name for _, field_name, _, _ in parsed if field_name is not None]
    unknown = {field_name for field_name in fields if field_name not in {"src", "exe"}}
    if unknown:
        raise ApiError(400, "language command contains unsupported placeholders")
    if any(format_spec or conversion for _, _, format_spec, conversion in parsed):
        raise ApiError(400, "language command contains unsupported formatting")
