"""Genre lists: which tracked games belong to one genre and theme, for example anime tower defense.

A list is a TOML file in lists/. It holds the signal words and Ronan's own decisions. The words give each game one
of three verdicts, with the reasons:

- in: Roblox files it under the genre, it shows the theme, and it shows no other theme.
- check: the signs disagree, so a person must decide.
- out: not the genre, or another theme, or no theme words at all.

Ronan's decisions in the file win over the words.
"""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .store import Store

IN, CHECK, OUT = "in", "check", "out"
CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z])")
NOT_WORD = re.compile(r"[^\w]+")


def normalize(text: str | None, split_camel: bool = True) -> str:
    """Lower case, words only: "[🎃UPD] AnimeReversal: Re:Zero's" -> "upd anime reversal re zeros"."""
    text = CAMEL.sub(" ", text or "") if split_camel else text or ""
    text = text.replace("'", "").replace("’", "")
    return " ".join(NOT_WORD.sub(" ", text.lower()).split())


def forms(text: str | None) -> tuple[str, str]:
    """Two normalized forms of one text: "AnimeReversal" needs the split, "CyGames" must stay whole."""
    return normalize(text), normalize(text, split_camel=False)


class Words:
    """A set of words and phrases. It finds each one as a whole word in normalized text."""

    def __init__(self, terms: list[str] | tuple[str, ...]):
        self.terms = tuple(dict.fromkeys(normalize(t) for t in terms if normalize(t)))
        latin = [t for t in self.terms if t.isascii()]
        self.other = [t for t in self.terms if not t.isascii()]  # for example アニメ: no spaces between words
        latin.sort(key=len, reverse=True)  # the longest phrase wins: "one punch man" before "one punch"
        self.pattern = re.compile(r"(?<!\w)(" + "|".join(map(re.escape, latin)) + r")(?!\w)") if latin else None

    def count(self, text: str | tuple[str, ...]) -> Counter:
        """How often each term occurs. For several forms of one text: the highest count of each term."""
        if isinstance(text, tuple):
            best: Counter = Counter()
            for form in text:
                best |= self.count(form)
            return best
        found: Counter = Counter()
        if self.pattern:
            found.update(match.group(1) for match in self.pattern.finditer(text))
        for term in self.other:
            if term in text:
                found[term] += text.count(term)
        return found


def _ids(table: dict) -> dict[int, str]:
    return {int(key): str(note) for key, note in (table or {}).items()}


@dataclass
class Rules:
    name: str
    title: str
    genre_l2: frozenset[str]
    genre_words: Words  # in the name: the genre when Roblox files the game elsewhere ("td", "tower defense")
    theme_words: Words  # general words: "anime", "waifu". One of them in the description alone is a weak sign.
    theme_names: Words  # franchises, characters, known titles: a strong sign anywhere
    weak_words: Words  # weak signs, for example the disclaimers that IP-inspired games use
    maybe_words: Words  # anime-style franchises (Vocaloid, Touhou): a person decides
    other_words: Words  # another theme: toilets, Five Nights, Undertale
    include: dict[int, str] = field(default_factory=dict)  # Ronan's decisions: universe id -> note
    exclude: dict[int, str] = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path) -> Rules:
        data = tomllib.loads(Path(path).read_text(encoding="utf-8"))
        genre, theme, other = data.get("genre", {}), data.get("theme", {}), data.get("other_theme", {})
        return cls(
            name=data["name"],
            title=data.get("title", data["name"]),
            genre_l2=frozenset(genre.get("genre_l2", [])),
            genre_words=Words(genre.get("name_words", [])),
            theme_words=Words(theme.get("words", [])),
            theme_names=Words(theme.get("franchises", []) + theme.get("characters", []) + theme.get("titles", [])),
            weak_words=Words(theme.get("weak", [])),
            maybe_words=Words(theme.get("maybe", [])),
            other_words=Words(other.get("words", [])),
            include=_ids(data.get("include")),
            exclude=_ids(data.get("exclude")),
        )

    @property
    def has_theme(self) -> bool:
        """A list without theme words is a genre-only list: the genre alone decides."""
        return any(w.terms for w in (self.theme_words, self.theme_names, self.weak_words, self.maybe_words))


def list_path(folder: str | Path, name: str) -> Path:
    return Path(folder) / f"{name}.toml"


@dataclass
class Decision:
    universe_id: int
    verdict: str
    reasons: list[str]
    by_hand: bool = False  # Ronan decided, not the words


def _merge(*founds: dict[str, Counter]) -> dict[str, Counter]:
    merged: dict[str, Counter] = {}
    for found in founds:
        for where, counter in found.items():
            merged[where] = merged.get(where, Counter()) + counter
    return merged


def _signs(found: dict[str, Counter]) -> str:
    """{"name": Counter(anime=1), "description": Counter(naruto=2)} -> "anime (name), naruto (description)"."""
    parts = [f"{term} ({where})" for where, counter in found.items() for term in counter]
    return ", ".join(parts)


def decide(rules: Rules, game: dict, description: str, own: bool = False) -> Decision:
    """The verdict for one game. `game` needs universe_id, name and genre_l2."""
    uid = game["universe_id"]
    if uid in rules.include:
        return Decision(uid, IN, [f"Ronan: {rules.include[uid]}"], by_hand=True)
    if uid in rules.exclude:
        return Decision(uid, OUT, [f"Ronan: {rules.exclude[uid]}"], by_hand=True)

    name, text = forms(game.get("name")), forms(description)
    genre = game.get("genre_l2") or ""
    in_genre = genre in rules.genre_l2
    genre_hint = rules.genre_words.count(name)

    def found(name_counts, text_counts) -> dict[str, Counter]:
        return {k: v for k, v in (("name", name_counts), ("description", text_counts)) if v}

    strong = found(rules.theme_words.count(name) + rules.theme_names.count(name), rules.theme_names.count(text))
    weak = found(Counter(), rules.theme_words.count(text) + rules.weak_words.count(text))
    maybe = found(rules.maybe_words.count(name), rules.maybe_words.count(text))
    other = found(rules.other_words.count(name), rules.other_words.count(text))
    weak_total = sum(weak["description"].values()) if weak else 0
    if strong or weak_total >= 2:
        theme, theme_found = "strong", strong or weak
    elif weak_total == 1 or maybe:
        theme, theme_found = "weak", _merge(maybe, weak)
    else:
        theme, theme_found = "none", {}

    reasons: list[str] = []
    if own:
        reasons.append("your own game")
    if not rules.has_theme:  # a genre-only list
        if in_genre:
            return Decision(uid, IN, reasons + [f"Roblox genre: {genre}"])
        if genre_hint:
            return Decision(uid, CHECK, reasons + [f"Roblox genre: {genre or 'none'}, but the name says "
                                                   f"{', '.join(genre_hint)}"])
        return Decision(uid, OUT, reasons + [f"Roblox genre: {genre or 'none'}"])
    if not in_genre:
        where = f"Roblox genre: {genre or 'none'}"
        if genre_hint and (theme != "none" or own):
            hint = ", ".join(genre_hint)
            reasons += [f"{where}, but the name says {hint}"] + ([f"theme: {_signs(theme_found)}"] if theme_found else [])
            return Decision(uid, CHECK, reasons)
        return Decision(uid, OUT, reasons + [f"not {rules.title.lower()}: {where}"])

    if theme == "strong" and not other:
        verdict = CHECK if own else IN
        return Decision(uid, verdict, reasons + [f"theme: {_signs(theme_found)}"])
    if theme != "none" and other:
        return Decision(uid, CHECK, reasons + [f"theme: {_signs(theme_found)}", f"other theme: {_signs(other)}"])
    if other:
        return Decision(uid, OUT, reasons + [f"other theme: {_signs(other)}"])
    if theme == "weak":
        return Decision(uid, CHECK, reasons + [f"weak sign: {_signs(theme_found)}"])
    return Decision(uid, CHECK if own else OUT, reasons + ["no theme words"])


def candidates(store: Store, day: str) -> list[dict]:
    """Every game saved on this day, with what a list decision and a review need."""
    cursor = store.db.execute(
        """SELECT g.universe_id, g.root_place_id, g.name, g.genre_l1, g.genre_l2, g.playing, g.visits, g.icon_url,
                  g.creator_name, g.universe_id IN (SELECT universe_id FROM game_sources WHERE source LIKE 'place:%')
                  AS own
           FROM game_daily g WHERE g.day = ? ORDER BY g.playing DESC, g.universe_id""",
        (day,),
    )
    names = [column[0] for column in cursor.description]
    return [dict(zip(names, row)) for row in cursor.fetchall()]


def build(store: Store, rules: Rules, day: str) -> list[tuple[dict, Decision]]:
    """Each game of the day with its decision, most players first."""
    texts = store.texts(day)
    return [
        (game, decide(rules, game, texts.get(game["universe_id"], ""), own=bool(game["own"])))
        for game in candidates(store, day)
    ]


def members(store: Store, rules: Rules, day: str) -> set[int]:
    """The universe ids in the list on this day: verdict "in" (the words) or included by Ronan."""
    return {game["universe_id"] for game, decision in build(store, rules, day) if decision.verdict == IN}
