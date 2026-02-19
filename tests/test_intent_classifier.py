from __future__ import annotations

from campus_assistant.nlp.intent import IntentClassifier


def test_intent_classifier_basic_cases() -> None:
    clf = IntentClassifier()

    assert clf.predict("Where is Sherman Hall?").label == "location"
    assert clf.predict("When is the Spring 2026 add/drop deadline?").label == "time"
    assert clf.predict("What events are happening today?").label == "event"
    assert clf.predict("Who teaches CMSC 601?").label == "class_schedule"
