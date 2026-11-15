"""
Password hashing and sign-in tokens. Standard library only (no new packages).

Passwords: scrypt with a random salt per password. The stored text looks like
    scrypt$16384$8$1$<salt>$<hash>
so the cost can be raised later and old hashes still verify.
Tokens: random, handed to the browser once. Only their SHA-256 hash is stored,
so a copy of the database cannot be used to sign in.
"""
import base64
import hashlib
import hmac
import os
import secrets

_N, _R, _P = 2 ** 14, 8, 1
_MAXMEM = 64 * 1024 * 1024


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM, dklen=32)
    return f"scrypt${_N}${_R}${_P}${_b64(salt)}${_b64(digest)}"


def verify_password(password: str, stored: str) -> bool:
    """True if the password matches. Never raises for a malformed stored value."""
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        actual = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt),
            n=int(n), r=int(r), p=int(p), maxmem=_MAXMEM, dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


# Checked when the name does not exist, so a wrong name and a wrong password
# take about the same time.
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
