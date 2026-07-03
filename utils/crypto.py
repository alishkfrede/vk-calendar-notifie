from cryptography.fernet import Fernet
import base64
import hashlib
from app.config import settings


def _get_fernet() -> Fernet:
    """Создаёт Fernet-ключ из ENCRYPTION_KEY."""
    # Хэшируем ключ до 32 байт и кодируем в base64
    key = hashlib.sha256(settings.ENCRYPTION_KEY.encode()).digest()
    fernet_key = base64.urlsafe_b64encode(key)
    return Fernet(fernet_key)


def encrypt_token(token: str) -> str:
    """Шифрует токен перед сохранением в БД."""
    f = _get_fernet()
    encrypted = f.encrypt(token.encode())
    return encrypted.decode()


def decrypt_token(encrypted_token: str) -> str:
    """Дешифрует токен из БД."""
    f = _get_fernet()
    decrypted = f.decrypt(encrypted_token.encode())
    return decrypted.decode()