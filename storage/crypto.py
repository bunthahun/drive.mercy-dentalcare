"""
AES-256-GCM Cryptographic Module for Secure Cloud Storage.
Protects files before uploading to cloud servers (Zero-Knowledge Privacy).
"""
import os
import hashlib
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

SALT_FIXED = b"Antigravity_5TB_Cloud_Storage_Salt_2026"

_DERIVED_KEYS = {}

def derive_key(passphrase: str) -> bytes:
    """Derive 256-bit AES key from a passphrase using PBKDF2 (cached for high performance)."""
    if passphrase in _DERIVED_KEYS:
        return _DERIVED_KEYS[passphrase]
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=SALT_FIXED,
        iterations=100000,
    )
    key = kdf.derive(passphrase.encode("utf-8"))
    _DERIVED_KEYS[passphrase] = key
    return key

def encrypt_bytes(data: bytes, key: bytes) -> bytes:
    """
    Encrypt data using AES-256-GCM.
    Returns: 12-byte Nonce + Ciphertext (which includes 16-byte GCM authentication tag).
    """
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, data, None)
    return nonce + ciphertext

def decrypt_bytes(encrypted_data: bytes, key: bytes) -> bytes:
    """
    Decrypt data encrypted by encrypt_bytes.
    Extracts 12-byte Nonce and decrypts ciphertext with tag validation.
    """
    if len(encrypted_data) < 12 + 16:
        raise ValueError("Invalid encrypted data length")
    nonce = encrypted_data[:12]
    ciphertext = encrypted_data[12:]
    aesgcm = AESGCM(key)
    return aesgcm.decrypt(nonce, ciphertext, None)

def compute_sha256(filepath: str) -> str:
    """Compute SHA-256 checksum of a file efficiently."""
    sha = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(1024 * 1024):  # 1MB blocks
            sha.update(chunk)
    return sha.hexdigest()
