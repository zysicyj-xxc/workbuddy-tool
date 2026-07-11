"""加密存储与数据包加解密

- 本地运行态：Fernet 密钥保存在 ~/.workbuddy-tool/secret.key（代理 JSON 等）
- 跨环境数据包：口令派生密钥（PBKDF2），盐写进包头，空库/新机器可导入
"""

import base64
import hashlib
import json
import os
from pathlib import Path

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

# 数据目录名（位于用户主目录下）
_DATA_DIR_NAME = ".workbuddy-tool"
# 密钥文件名
_KEY_FILE_NAME = "secret.key"

# 跨环境数据包魔数与版本
_PKG_MAGIC = b"WBDP"
_PKG_VERSION = 3
_PKG_SALT_LEN = 16
_PKG_ITERATIONS = 390000

# 默认口令仅用于本地开发；生产请设 DATA_PACKAGE_PASSWORD
_DEFAULT_PACKAGE_PASSWORD = "workbuddy-change-me"


def get_data_dir() -> Path:
    """获取数据目录路径（不存在则创建）

    返回 ~/.workbuddy-tool 目录。如果用户主目录不可写，
    回退到项目根目录下的 data 目录。
    """
    app_dir = Path.home() / _DATA_DIR_NAME
    try:
        app_dir.mkdir(exist_ok=True)
    except OSError:
        project_dir = Path(__file__).parent.parent.parent
        app_dir = project_dir / "data"
        app_dir.mkdir(exist_ok=True)
    return app_dir


def get_or_create_key() -> bytes:
    """获取或自动生成 Fernet 加密密钥（本机 secret.key）"""
    key_path = get_data_dir() / _KEY_FILE_NAME
    if key_path.exists():
        return key_path.read_bytes()
    key = Fernet.generate_key()
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        pass
    return key


def _get_fernet() -> Fernet:
    return Fernet(get_or_create_key())


def get_package_password(explicit: str | None = None) -> str:
    """数据包口令：显式参数 > 环境变量 > 默认开发口令"""
    if explicit is not None and str(explicit).strip():
        return str(explicit).strip()
    env = os.environ.get("DATA_PACKAGE_PASSWORD", "").strip()
    if env:
        return env
    return _DEFAULT_PACKAGE_PASSWORD


def _fernet_from_password(password: str, salt: bytes) -> Fernet:
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=salt,
        iterations=_PKG_ITERATIONS,
    )
    key = base64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))
    return Fernet(key)


def encrypt_json(data: dict) -> bytes:
    """本机密钥加密（兼容旧逻辑，不推荐跨机器传包）"""
    f = _get_fernet()
    json_bytes = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    return f.encrypt(json_bytes)


def decrypt_json(encrypted: bytes) -> dict:
    """本机密钥解密。失败返回空 dict。"""
    f = _get_fernet()
    try:
        json_bytes = f.decrypt(encrypted)
        return json.loads(json_bytes.decode("utf-8"))
    except Exception:
        return {}


def encrypt_package(data: dict, password: str | None = None) -> bytes:
    """导出跨环境数据包：WBDP + version + salt + Fernet(token)"""
    pwd = get_package_password(password)
    salt = os.urandom(_PKG_SALT_LEN)
    f = _fernet_from_password(pwd, salt)
    payload = json.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
    token = f.encrypt(payload)
    return _PKG_MAGIC + bytes([_PKG_VERSION]) + salt + token


def decrypt_package(blob: bytes, password: str | None = None) -> dict:
    """解密数据包。优先识别 WBDP v3；否则回退本机密钥（旧 .enc）。

    若显式传入 password，则只尝试该口令（不回退环境变量），避免误判。
    """
    if not blob:
        return {}

    if len(blob) > 5 + _PKG_SALT_LEN and blob[:4] == _PKG_MAGIC:
        version = blob[4]
        if version != _PKG_VERSION:
            return {}
        salt = blob[5 : 5 + _PKG_SALT_LEN]
        token = blob[5 + _PKG_SALT_LEN :]
        if password is not None and str(password).strip():
            candidates = [str(password).strip()]
        else:
            candidates = [get_package_password(None)]
        for pwd in candidates:
            try:
                f = _fernet_from_password(pwd, salt)
                raw = f.decrypt(token)
                return json.loads(raw.decode("utf-8"))
            except Exception:
                continue
        return {}

    return decrypt_json(blob)


def encrypt_file(filepath: str, data: dict):
    """加密写入文件（本机密钥）"""
    encrypted = encrypt_json(data)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "wb") as fp:
        fp.write(encrypted)
    os.replace(tmp_path, filepath)


def decrypt_file(filepath: str) -> dict:
    """从文件解密读取（本机密钥）"""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "rb") as fp:
            encrypted = fp.read()
        return decrypt_json(encrypted)
    except Exception:
        return {}


def package_fingerprint(password: str | None = None) -> str:
    """调试用：口令指纹（不回传明文）"""
    pwd = get_package_password(password)
    return hashlib.sha256(pwd.encode("utf-8")).hexdigest()[:12]
