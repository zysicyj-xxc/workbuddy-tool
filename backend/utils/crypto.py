"""加密存储工具 - 使用 Fernet 对称加密保护敏感数据"""

import json
import os
from pathlib import Path

from cryptography.fernet import Fernet

# 数据目录名（位于用户主目录下）
_DATA_DIR_NAME = ".workbuddy-tool"
# 密钥文件名
_KEY_FILE_NAME = "secret.key"


def get_data_dir() -> Path:
    """获取数据目录路径（不存在则创建）

    返回 ~/.workbuddy-tool 目录。如果用户主目录不可写，
    回退到项目根目录下的 data 目录。
    """
    app_dir = Path.home() / _DATA_DIR_NAME
    try:
        app_dir.mkdir(exist_ok=True)
    except OSError:
        # 用户目录不可写时回退到项目目录
        project_dir = Path(__file__).parent.parent.parent
        app_dir = project_dir / "data"
        app_dir.mkdir(exist_ok=True)
    return app_dir


def get_or_create_key() -> bytes:
    """获取或自动生成 Fernet 加密密钥

    读取 ~/.workbuddy-tool/secret.key，如果不存在则自动生成
    新的 Fernet 密钥并保存到文件。

    Returns:
        bytes: Fernet 密钥（base64 编码）
    """
    key_path = get_data_dir() / _KEY_FILE_NAME
    if key_path.exists():
        return key_path.read_bytes()
    # 生成新密钥并保存
    key = Fernet.generate_key()
    # 以 0600 权限保存（仅所有者可读写）
    key_path.write_bytes(key)
    try:
        os.chmod(key_path, 0o600)
    except OSError:
        # Windows 上 chmod 行为不同，忽略错误
        pass
    return key


def _get_fernet() -> Fernet:
    """获取 Fernet 实例"""
    return Fernet(get_or_create_key())


def encrypt_json(data: dict) -> bytes:
    """将 dict 序列化为 JSON 并用 Fernet 加密

    Args:
        data: 要加密的字典

    Returns:
        bytes: 加密后的字节数据
    """
    f = _get_fernet()
    json_bytes = json.dumps(data, ensure_ascii=False).encode("utf-8")
    return f.encrypt(json_bytes)


def decrypt_json(encrypted: bytes) -> dict:
    """用 Fernet 解密并反序列化为 dict

    Args:
        encrypted: 加密的字节数据

    Returns:
        dict: 解密后的字典。解密失败时返回空 dict。
    """
    f = _get_fernet()
    try:
        json_bytes = f.decrypt(encrypted)
        return json.loads(json_bytes.decode("utf-8"))
    except Exception:
        return {}


def encrypt_file(filepath: str, data: dict):
    """加密写入文件

    将 dict 加密后写入指定文件（原子写入，避免读到半截数据）。

    Args:
        filepath: 目标文件路径
        data: 要加密保存的字典
    """
    encrypted = encrypt_json(data)
    tmp_path = filepath + ".tmp"
    with open(tmp_path, "wb") as fp:
        fp.write(encrypted)
    # 原子 rename（Windows 上 os.replace 是原子的）
    os.replace(tmp_path, filepath)


def decrypt_file(filepath: str) -> dict:
    """从文件解密读取

    Args:
        filepath: 加密文件路径

    Returns:
        dict: 解密后的字典。文件不存在或解密失败时返回空 dict。
    """
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "rb") as fp:
            encrypted = fp.read()
        return decrypt_json(encrypted)
    except Exception:
        return {}
