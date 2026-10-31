"""Correction prudente des fautes de frappe : « abeshe » -> « abeche », « sorgo » -> « sorgho ».

Seuls les mots de 5 lettres ou plus qui ne sont PAS déjà connus sont corrigés, vers le mot de vocabulaire
le plus proche (même première lettre, ressemblance >= 0,84 ; 0,80 dès 6 lettres). Mieux vaut laisser passer une faute que
transformer un vrai mot : une liste de mots courants est protégée."""
from __future__ import annotations

import difflib
import re

CUTOFF = 0.84
CUTOFF_LONG = 0.80
MIN_LEN = 5

# mots français courants proches d'un mot du vocabulaire : jamais corrigés
PROTECTED = frozenset("""famille famine mange manger marche marches marque mercredi matin morale mille milieu pluies plein
prendre prends prix sel selon sera serai sucre suite sujet salut salam toujours toute temps tarte rizieres
mois moins moyen mobile article arrive arriver abord achat acheter acheteur acheteurs aider aide
cher chez chose choses chaque chaud tchad tchadien tchadienne ville villes village villages
quel quelle quels quelles quand quoi comme comment combien contre dans donne donner donnees depuis
vendre vendeur vendeurs vente ventes voir veux voudrais voulez prix produit produits petit petite grand grande
pouvez pourrait pourquoi peut cette cela celui celle ceux avec avoir ainsi aussi autre autres encore entre""".split())

_TOKEN = re.compile(r"[a-z0-9']+")


def fix(norm: str, vocabulary: set[str]) -> tuple[str, list[tuple[str, str]]]:
    """(texte corrigé, [(mot lu, mot corrigé)]). `norm` est déjà normalisé (minuscules, sans accents)."""
    by_letter: dict[str, list[str]] = {}
    for w in vocabulary:
        if len(w) >= 4:
            by_letter.setdefault(w[0], []).append(w)
    fixes: list[tuple[str, str]] = []

    def repl(m: re.Match) -> str:
        word = m.group(0)
        if len(word) < MIN_LEN or word in vocabulary or word in PROTECTED or word.isdigit():
            return word
        near = difflib.get_close_matches(word, by_letter.get(word[0], []), n=1, cutoff=CUTOFF if len(word) < 6 else CUTOFF_LONG)
        if not near or len(near[0]) < MIN_LEN or abs(len(near[0]) - len(word)) > 2:
            return word
        fixes.append((word, near[0]))
        return near[0]

    return _TOKEN.sub(repl, norm), fixes
