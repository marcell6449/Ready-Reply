"""Random session tokens. Only their SHA-256 hash is stored."""

import hashlib
import secrets

TOKEN_BYTES = 32


class SecureTokenService:
    def new_token(self) -> str:
        return secrets.token_urlsafe(TOKEN_BYTES)

    def hash_token(self, token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()
