from __future__ import annotations

import re
from dataclasses import asdict, dataclass

from rapidfuzz import fuzz
from spellchecker import SpellChecker

from campus_assistant.data_models import Document

_TOKEN_RE = re.compile(r"[A-Za-z]+(?:'[A-Za-z]+)?|\d+|[^\w\s]")
_ALPHA_RE = re.compile(r"^[A-Za-z]+(?:'[A-Za-z]+)?$")
_VOCAB_RE = re.compile(r"[a-z]{3,}")


@dataclass
class NormalizedQuery:
    original: str
    corrected: str
    applied: bool
    changes: list[dict[str, str]]

    def to_dict(self) -> dict[str, str | bool | list[dict[str, str]]]:
        return asdict(self)


class QueryNormalizer:
    COURSE_PREFIXES = {
        "AFST",
        "ANTH",
        "ART",
        "BIOL",
        "CHEM",
        "CMSC",
        "DATA",
        "ECON",
        "EDUC",
        "ENGL",
        "GWST",
        "HIST",
        "IS",
        "MATH",
        "ME",
        "PHYS",
        "POLI",
        "PSYC",
        "SOCY",
        "STAT",
    }

    SHORTCUTS = {
        "whr": "where",
        "wen": "when",
        "wut": "what",
        "plz": "please",
        "tmrw": "tomorrow",
        "dept": "department",
        "prof": "professor",
        "sched": "schedule",
        "calender": "calendar",
        "dline": "deadline",
        "reg": "registration",
    }

    DOMAIN_TERMS = {
        "umbc",
        "sondheim",
        "sherman",
        "ite",
        "retriever",
        "registrar",
        "campus",
        "academic",
        "calendar",
        "deadlines",
        "deadline",
        "commons",
        "library",
        "engineering",
        "university",
        "center",
        "event",
        "events",
        "semester",
        "undergraduate",
        "graduate",
        "spring",
        "summer",
        "fall",
        "winter",
        "room",
        "building",
        "transit",
        "dining",
        "facilities",
        "schedule",
        "schedules",
        "class",
        "classes",
        "course",
        "courses",
        "section",
        "sections",
    }

    def __init__(self) -> None:
        self.spellchecker = SpellChecker(distance=2)
        self.known_terms = set(self.DOMAIN_TERMS)
        self.known_terms.update(prefix.lower() for prefix in self.COURSE_PREFIXES)
        self.spellchecker.word_frequency.load_words(self.known_terms)

    def bootstrap_from_documents(self, documents: list[Document]) -> None:
        learned: set[str] = set()
        for doc in documents:
            for blob in [doc.title, doc.text]:
                for token in _VOCAB_RE.findall(blob.lower()):
                    if len(token) > 2:
                        learned.add(token)

        if learned:
            self.known_terms.update(learned)
            self.spellchecker.word_frequency.load_words(learned)

    def normalize(self, query: str) -> NormalizedQuery:
        original = " ".join(query.strip().split())
        if not original:
            return NormalizedQuery(original=query, corrected=query, applied=False, changes=[])

        normalized = self._normalize_course_codes(original)
        tokens = _TOKEN_RE.findall(normalized)

        output_tokens: list[str] = []
        changes: list[dict[str, str]] = []

        for token in tokens:
            if not _ALPHA_RE.match(token):
                output_tokens.append(token)
                continue

            lowered = token.lower()
            if lowered in self.SHORTCUTS:
                replacement = _match_case(token, self.SHORTCUTS[lowered])
                output_tokens.append(replacement)
                if replacement != token:
                    changes.append({"from": token, "to": replacement})
                continue

            if len(lowered) <= 2 or lowered in self.known_terms:
                output_tokens.append(token)
                continue

            if lowered in self.spellchecker:
                output_tokens.append(token)
                continue

            candidate = self.spellchecker.correction(lowered)
            if not candidate:
                output_tokens.append(token)
                continue

            if candidate != lowered and fuzz.ratio(lowered, candidate) >= 80:
                replacement = _match_case(token, candidate)
                output_tokens.append(replacement)
                changes.append({"from": token, "to": replacement})
            else:
                output_tokens.append(token)

        corrected = self._join_tokens(output_tokens)
        corrected = self._normalize_course_codes(corrected)
        corrected = " ".join(corrected.split())

        applied = corrected.lower() != original.lower()
        return NormalizedQuery(original=original, corrected=corrected, applied=applied, changes=changes)

    def _normalize_course_codes(self, text: str) -> str:
        pattern = re.compile(r"\b([A-Za-z]{2,5})\s*-?\s*(\d{3}[A-Za-z]?)\b")

        def repl(match: re.Match[str]) -> str:
            prefix = match.group(1).upper()
            number = match.group(2).upper()
            if prefix in self.COURSE_PREFIXES:
                return f"{prefix} {number}"
            return match.group(0)

        return pattern.sub(repl, text)

    @staticmethod
    def _join_tokens(tokens: list[str]) -> str:
        if not tokens:
            return ""

        out: list[str] = []
        no_space_before = {".", ",", "?", "!", ":", ";", ")", "]", "}"}
        no_space_after = {"(", "[", "{"}

        for token in tokens:
            if not out:
                out.append(token)
                continue

            prev = out[-1]
            if token in no_space_before:
                out[-1] = prev + token
            elif prev and prev[-1] in no_space_after:
                out[-1] = prev + token
            else:
                out.append(" " + token)

        return "".join(out)


def _match_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source.istitle():
        return replacement.title()
    return replacement
