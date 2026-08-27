"""Hash de senha e verificacao (PBKDF2-SHA256, sem dependencia externa)."""

import hashlib
import hmac
import os

ITERACOES = 260_000


def gerar_hash(senha: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", senha.encode("utf-8"), salt, ITERACOES)
    return f"pbkdf2_sha256${ITERACOES}${salt.hex()}${dk.hex()}"


def verificar_senha(senha: str, senha_hash: str) -> bool:
    try:
        algoritmo, iteracoes, salt_hex, hash_hex = senha_hash.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac(
            "sha256", senha.encode("utf-8"), bytes.fromhex(salt_hex), int(iteracoes)
        )
        return hmac.compare_digest(dk.hex(), hash_hex)
    except Exception:
        return False
