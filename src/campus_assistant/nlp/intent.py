from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class IntentPrediction:
    label: str
    confidence: float


class IntentClassifier:
    """
    Lightweight intent classifier tuned for campus QA.

    The baseline uses interpretable rules to avoid brittle ML on low-resource labels.
    """

    INTENT_PATTERNS: dict[str, list[str]] = {
        "location": [
            r"\bwhere\b",
            r"\blocate\b",
            r"\bdirections?\b",
            r"\bbuilding\b",
            r"\broom\b",
            r"\bmap\b",
        ],
        "time": [
            r"\bwhen\b",
            r"\btime\b",
            r"\btoday\b",
            r"\btomorrow\b",
            r"\bdeadline\b",
            r"\bhours\b",
        ],
        "event": [
            r"\bevents?\b",
            r"\bworkshop\b",
            r"\bseminar\b",
            r"\btalk\b",
            r"\bfree food\b",
            r"\bclub\b",
        ],
        "class_schedule": [
            r"\bclass\b",
            r"\bcourse\b",
            r"\bsection\b",
            r"\binstructor\b",
            r"\bsyllabus\b",
            r"\bregister\b",
            r"\bcmsc\s*\d+\b",
            r"\bdata\s*\d+\b",
        ],
        "facility_hours": [
            r"\blibrary\b",
            r"\bdining\b",
            r"\bgym\b",
            r"\bcommons\b",
            r"\bopen\b",
            r"\bclose\b",
        ],
    }

    def predict(self, query: str) -> IntentPrediction:
        text = query.lower()
        scores: dict[str, int] = {}

        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                if re.search(pattern, text):
                    score += 1
            if score > 0:
                scores[intent] = score

        # Resolve common mixed-intent phrasing such as "events today".
        if "event" in scores and re.search(r"\bevents?\b", text):
            scores["event"] += 1

        if not scores:
            return IntentPrediction(label="general", confidence=0.35)

        best_intent = max(scores, key=scores.get)
        total = sum(scores.values())
        confidence = round(scores[best_intent] / total, 3)
        return IntentPrediction(label=best_intent, confidence=confidence)
