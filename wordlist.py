#!/usr/bin/env python3
"""
CEFR B1 vocabulary guard (Python stdlib only).

Loads the Cambridge B1 Preliminary / Preliminary for Schools vocabulary list
(extracted from "CEFR B1-preliminary-vocabulary-list.pdf" into
data/cefr_b1_wordlist.json) and offers two things:

  1. prompt_block()      -> the allowed-words text injected into the worksheet
                            generation prompt, so the AI only writes with
                            B1-and-below vocabulary.
  2. check_text(text)    -> the words in a generated text that are NOT on the
                            list (after stripping normal inflections), so the
                            guardrail can flag them to the teacher.

Capitalised tokens (names, places, days) and numbers are never flagged.
"""

import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
WORDLIST_FILE = os.path.join(ROOT, "data", "cefr_b1_wordlist.json")

# grammar words the tokenizer may produce from contractions
_CONTRACTIONS = {
    "n't": "not", "'re": "are", "'ve": "have", "'ll": "will",
    "'d": "would", "'m": "am", "'s": "",  # possessive/is — check base word only
}

# irregular surface form -> base form (only bases that are on the B1 list)
_IRREGULAR = {
    "am": "be", "is": "be", "are": "be", "was": "be", "were": "be",
    "been": "be", "being": "be",
    "has": "have", "had": "have", "does": "do", "did": "do", "done": "do",
    "goes": "go", "went": "go", "gone": "go",
    "became": "become", "began": "begin", "begun": "begin", "bent": "bend",
    "bit": "bite", "bitten": "bite", "blew": "blow", "blown": "blow",
    "broke": "break", "broken": "break", "brought": "bring", "built": "build",
    "burnt": "burn", "bought": "buy", "caught": "catch", "chose": "choose",
    "chosen": "choose", "came": "come", "dealt": "deal", "dug": "dig",
    "drew": "draw", "drawn": "draw", "dreamt": "dream", "drank": "drink",
    "drunk": "drink", "drove": "drive", "driven": "drive", "ate": "eat",
    "eaten": "eat", "fell": "fall", "fallen": "fall", "fed": "feed",
    "felt": "feel", "fought": "fight", "found": "find", "flew": "fly",
    "flown": "fly", "forgot": "forget", "forgotten": "forget",
    "forgave": "forgive", "forgiven": "forgive", "froze": "freeze",
    "frozen": "freeze", "got": "get", "gotten": "get", "gave": "give",
    "given": "give", "grew": "grow", "grown": "grow", "hung": "hang",
    "heard": "hear", "hid": "hide", "hidden": "hide", "held": "hold",
    "kept": "keep", "knew": "know", "known": "know", "laid": "lay",
    "led": "lead", "learnt": "learn", "left": "leave", "lent": "lend",
    "lay": "lie", "lain": "lie", "lit": "light", "lost": "lose",
    "made": "make", "meant": "mean", "met": "meet", "paid": "pay",
    "rode": "ride", "ridden": "ride", "rang": "ring", "rung": "ring",
    "rose": "rise", "risen": "rise", "ran": "run", "said": "say",
    "saw": "see", "seen": "see", "sold": "sell", "sent": "send",
    "shook": "shake", "shaken": "shake", "shone": "shine", "shot": "shoot",
    "shown": "show", "sang": "sing", "sung": "sing", "sank": "sink",
    "sat": "sit", "slept": "sleep", "smelt": "smell", "spoke": "speak",
    "spoken": "speak", "spelt": "spell", "spent": "spend", "spilt": "spill",
    "stood": "stand", "stole": "steal", "stolen": "steal", "stuck": "stick",
    "swam": "swim", "swum": "swim", "took": "take", "taken": "take",
    "taught": "teach", "tore": "tear", "torn": "tear", "told": "tell",
    "thought": "think", "threw": "throw", "thrown": "throw",
    "understood": "understand", "woke": "wake", "woken": "wake",
    "wore": "wear", "worn": "wear", "won": "win", "wrote": "write",
    "written": "write",
    "children": "child", "men": "man", "women": "woman", "people": "person",
    "feet": "foot", "teeth": "tooth", "mice": "mouse",
    "better": "good", "best": "good", "worse": "bad", "worst": "bad",
    "more": "many", "most": "many", "less": "little", "least": "little",
    "further": "far", "farther": "far",
}

_cache = None


def load():
    """Return the allowed-word set (lowercased). Empty set if the file is missing."""
    global _cache
    if _cache is None:
        try:
            with open(WORDLIST_FILE, encoding="utf-8") as f:
                data = json.load(f)
            words = {w.strip().lower() for w in data.get("words", []) if w.strip()}
        except (OSError, ValueError):
            words = set()
        _cache = words
    return _cache


def display_words():
    """The word list in its display form (for prompts / pushing to the DB)."""
    try:
        with open(WORDLIST_FILE, encoding="utf-8") as f:
            return json.load(f).get("words", [])
    except (OSError, ValueError):
        return []


def available():
    return bool(load())


# --------------------------------------------------------------------------
# Inflection stripping — candidate base forms for a surface word
# --------------------------------------------------------------------------
def _candidates(word):
    w = word.lower()
    out = {w}
    if w in _IRREGULAR:
        out.add(_IRREGULAR[w])
    # contractions
    for suf, repl in _CONTRACTIONS.items():
        if w.endswith(suf) and len(w) > len(suf):
            out.add(w[: -len(suf)])
            if repl:
                out.add(repl)
    # plural / 3rd person: -s, -es, -ies; knives -> knife
    if w.endswith("ies") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("ves") and len(w) > 4:
        out.add(w[:-3] + "f")
        out.add(w[:-3] + "fe")
    if w.endswith("es") and len(w) > 3:
        out.add(w[:-2])
    if w.endswith("s") and len(w) > 2:
        out.add(w[:-1])
    # past: -ed, -d, -ied
    if w.endswith("ied") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("ed") and len(w) > 3:
        out.add(w[:-2])          # walked -> walk
        out.add(w[:-1])          # liked  -> like
        if len(w) > 4 and w[-3] == w[-4]:
            out.add(w[:-3])      # stopped -> stop
    # progressive: -ing
    if w.endswith("ing") and len(w) > 4:
        out.add(w[:-3])          # walking -> walk
        out.add(w[:-3] + "e")    # making  -> make
        if len(w) > 5 and w[-4] == w[-5]:
            out.add(w[:-4])      # running -> run
    # comparative / superlative: -er, -est, -ier, -iest
    if w.endswith("ier") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("iest") and len(w) > 5:
        out.add(w[:-4] + "y")
    if w.endswith("er") and len(w) > 3:
        out.add(w[:-2])
        out.add(w[:-1])          # nicer -> nice
    if w.endswith("est") and len(w) > 4:
        out.add(w[:-3])
        out.add(w[:-2])          # nicest -> nice
    # adverbs: -ly, -ily
    if w.endswith("ily") and len(w) > 4:
        out.add(w[:-3] + "y")
    if w.endswith("ly") and len(w) > 3:
        out.add(w[:-2])
    return out


_TOKEN_RE = re.compile(r"[A-Za-z]+(?:['’-][A-Za-z]+)*")


def check_text(text):
    """Return sorted out-of-list words found in `text` (lowercased, deduped).

    Skips capitalised tokens (proper nouns, days, places), numbers, and
    single letters (option labels). Hyphenated words pass when the whole
    word OR every part is allowed.
    """
    allowed = load()
    if not allowed or not text:
        return []
    flagged = set()
    for tok in _TOKEN_RE.findall(str(text)):
        if len(tok) < 2 or tok[0].isupper():
            continue
        if _is_allowed(tok, allowed):
            continue
        flagged.add(tok.lower())
    return sorted(flagged)


def _is_allowed(tok, allowed):
    low = tok.lower().replace("’", "'")
    if _candidates(low) & allowed:
        return True
    if "-" in low or "'" in low:
        parts = re.split(r"[-']", low)
        if all(not p or _candidates(p) & allowed for p in parts):
            return True
    return False


def check_worksheet(worksheet):
    """Scan every question's text, options and feedback. Returns a list of
    {"no": ..., "words": [...]} entries, one per question with flagged words."""
    out = []
    for q in (worksheet or {}).get("soalan", []) or []:
        if not isinstance(q, dict):
            continue
        blob = " ".join(
            [str(q.get("soalan") or ""), str(q.get("maklum_balas") or "")]
            + [str(p) for p in (q.get("pilihan") or [])]
        )
        words = check_text(blob)
        if words:
            out.append({"no": q.get("no", "?"), "words": words})
    return out


def prompt_block(max_chars=60000):
    """The allowed-vocabulary section appended to the worksheet system prompt."""
    words = display_words()
    if not words:
        return ""
    listing = ", ".join(words)[:max_chars]
    return (
        "\n\nVOCABULARY CONSTRAINT (STRICT):\n"
        "Pupils are CEFR B1 and below. Every word you write in questions, "
        "options, instructions and feedback MUST come from the Cambridge B1 "
        "Preliminary vocabulary list below (normal inflections such as plurals, "
        "-ed, -ing, -er/-est, -ly are fine, and proper nouns such as names of "
        "people and places are allowed). Do NOT use any word outside this list.\n\n"
        "ALLOWED WORDS:\n" + listing + "\n"
    )
