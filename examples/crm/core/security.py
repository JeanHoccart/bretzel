"""core/security — le hachage de mot de passe. Bibliothèque standard, rien d'autre.

**C'est l'app qui possède ça, et c'est écrit dans le framework** :
``bretzel.auth`` dit en toutes lettres « Bretzel doesn't model users beyond
their string ID. Apps own their profile / role / password machinery ». Les
quatre fonctions qu'il expose se contentent de se souvenir *quel* identifiant
est connecté, dans un cookie signé — elles ne savent pas ce qu'est un mot de
passe, et ne doivent pas le savoir.

Ce module est donc la moitié que le CRM apporte. Il tient en deux fonctions
parce que ``hashlib`` fait tout le travail :

- **PBKDF2-HMAC-SHA256**, 240 000 itérations, sel de 16 octets par
  utilisateur. Pas d'argon2 ni de bcrypt : ce sont des dépendances, et le
  charter tient à ce qu'un exemple n'en ajoute aucune. PBKDF2 est dans la
  bibliothèque standard depuis toujours et reste une réponse acceptable ;
- **comparaison en temps constant** (``hmac.compare_digest``). Un ``==`` sur
  des empreintes fuit leur préfixe commun par le temps de réponse.

⚠️ Le format stocké porte SES paramètres (``pbkdf2_sha256$<iters>$<sel>$<clé>``)
plutôt que de les lire d'une constante du module. C'est ce qui permet
d'augmenter le nombre d'itérations plus tard sans invalider les comptes
existants : chaque empreinte sait comment elle a été calculée.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

#: Le coût d'aujourd'hui. Il vit dans l'empreinte, pas seulement ici — cf.
#: la docstring du module.
ITERATIONS = 240_000
ALGORITHM = "pbkdf2_sha256"


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """``pbkdf2_sha256$<itérations>$<sel hex>$<clé hex>``.

    ``salt=`` n'est là que pour le semis, qui doit être **déterministe** :
    deux machines qui sèment la même base doivent obtenir les mêmes lignes.
    Un compte créé par l'app, lui, prend toujours un sel aléatoire.
    """
    if salt is None:
        salt = secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt, ITERATIONS
    )
    return f"{ALGORITHM}${ITERATIONS}${salt.hex()}${derived.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """Le mot de passe correspond-il à l'empreinte stockée ?

    Renvoie ``False`` sur une empreinte malformée plutôt que de lever : une
    ligne abîmée en base ne doit pas devenir une 500 sur la page de
    connexion, où elle serait un signal pour qui la provoque.
    """
    try:
        algorithm, iterations, salt_hex, expected_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            int(iterations),
        )
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(derived.hex(), expected_hex)
