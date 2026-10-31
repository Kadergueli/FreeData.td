"""Garde-fous : ce que l'assistant refuse de faire, avant même de chercher une réponse.

Principe : l'assistant ne parle que de données chiffrées (prix, météo). Il reste poli, ne
polémique jamais, n'exprime aucune opinion, et ne reprend pas le sujet d'une provocation.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.assistant.text import find_alias, normalize

MAX_QUESTION_CHARS = 300

# Insultes courantes (français, anglais, arabe tchadien translittéré) — mots entiers, normalisés.
_ABUSE = (
    "con", "conne", "connard", "connasse", "salope", "pute", "putain", "merde", "encule", "enculer",
    "idiot", "idiote", "imbecile", "debile", "stupide", "abruti", "cretin", "batard", "ordure",
    "fils de pute", "ta gueule", "ferme ta gueule", "va te faire", "nique", "niquer",
    "fuck", "fucking", "shit", "bitch", "asshole", "stupid", "idiot", "kalb", "hmar", "ibn el kalb",
)

# Sujets sur lesquels l'assistant n'a rien à dire : pas de données, risque de polémique.
_SENSITIVE = (
    "president", "gouvernement", "ministre", "politique", "parti", "election", "elections", "opposition",
    "coup d'etat", "armee", "militaire", "rebelles", "rebelle", "boko haram", "terroriste", "terroristes",
    "guerre", "religion", "musulman", "musulmans", "chretien", "chretiens", "islam", "christianisme",
    "ethnie", "ethnies", "tribu", "tribus", "sara", "arabe", "arabes", "gorane", "toubou",
    "homosexuel", "homosexuels", "lgbt", "sexe", "porno", "pornographie",
    "arme", "armes", "bombe", "drogue", "tuer", "assassiner",
)

# Détresse : on répond avec bienveillance, pas avec des données.
_DISTRESS = ("suicide", "me suicider", "me tuer", "mourir", "en finir", "je veux mourir")

# Tentatives de détourner l'assistant.
_INJECTION = ("ignore tes instructions", "ignore les instructions", "ignore toutes tes instructions", "oublie tes instructions",
              "tu es maintenant", "fais semblant", "mode developpeur", "system prompt", "prompt systeme",
              "ignore previous", "act as", "jailbreak")

GREETINGS = ("bonjour", "bonsoir", "salut", "salam", "salam aleykoum", "coucou", "hello", "hi", "bjr", "merci", "aide", "help", "menu", "ca va")


@dataclass(frozen=True)
class Verdict:
    kind: str            # "ok" | "empty" | "too_long" | "abuse" | "distress" | "injection"
    sensitive: bool = False


def _any(norm: str, words) -> bool:
    return any(find_alias(norm, normalize(w)) for w in words)


def check(question: str) -> Verdict:
    """Premier filtre. 'sensitive' signale un sujet délicat : l'assistant ne répondra que si la
    question contient AUSSI une demande de données (prix, météo), et sans commenter le sujet."""
    raw = str(question or "").strip()
    if not raw:
        return Verdict("empty")
    if len(raw) > MAX_QUESTION_CHARS:
        return Verdict("too_long")
    norm = normalize(raw)
    if _any(norm, _DISTRESS):
        return Verdict("distress")
    if _any(norm, _INJECTION):
        return Verdict("injection")
    if _any(norm, _ABUSE):
        return Verdict("abuse")
    return Verdict("ok", sensitive=_any(norm, _SENSITIVE))


def is_greeting(norm: str) -> bool:
    return _any(norm, GREETINGS)
