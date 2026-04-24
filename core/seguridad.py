import os
import hashlib
import hmac
import base64


def generar_hash_password(password):
    salt = os.urandom(16)
    iteraciones = 260000

    hash_bytes = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        iteraciones
    )

    salt_b64 = base64.b64encode(salt).decode("utf-8")
    hash_b64 = base64.b64encode(hash_bytes).decode("utf-8")

    return f"pbkdf2_sha256${iteraciones}${salt_b64}${hash_b64}"


def verificar_password(password, password_hash):
    try:
        algoritmo, iteraciones, salt_b64, hash_b64 = password_hash.split("$")

        if algoritmo != "pbkdf2_sha256":
            return False

        salt = base64.b64decode(salt_b64)
        hash_guardado = base64.b64decode(hash_b64)

        hash_calculado = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt,
            int(iteraciones)
        )

        return hmac.compare_digest(hash_guardado, hash_calculado)

    except Exception:
        return False