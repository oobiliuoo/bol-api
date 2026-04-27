from cryptography.fernet import Fernet
from app.config import settings


def get_fernet_key() -> bytes:
    """将配置的加密密钥转换为 Fernet 格式"""
    key = settings.encryption_key.encode()
    # Fernet 需要 32 字节的 base64 编码密钥
    # 使用 SHA256 哈希确保密钥长度正确
    import hashlib
    hashed = hashlib.sha256(key).digest()
    import base64
    return base64.urlsafe_b64encode(hashed)


_fernet = None


def get_fernet() -> Fernet:
    """获取 Fernet 实例"""
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_fernet_key())
    return _fernet


def encrypt_key(key: str) -> str:
    """加密 API Key"""
    return get_fernet().encrypt(key.encode()).decode()


def decrypt_key(encrypted: str) -> str:
    """解密 API Key"""
    return get_fernet().decrypt(encrypted.encode()).decode()


def is_encrypted(value: str) -> bool:
    """检查值是否已加密"""
    # Fernet 加密后的值以特定前缀开头
    try:
        get_fernet().decrypt(value.encode())
        return True
    except Exception:
        return False