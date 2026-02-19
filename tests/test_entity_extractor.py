from __future__ import annotations

from campus_assistant.nlp.entity_extractor import CampusEntityExtractor


def test_entity_extractor_detects_course_and_building() -> None:
    extractor = CampusEntityExtractor()
    entities = extractor.extract("Where is CMSC 601 in Sherman Hall room 204?")

    labels = {entity.label for entity in entities}
    texts = {entity.text.upper() for entity in entities}

    assert "COURSE_CODE" in labels
    assert "BUILDING" in labels
    assert any("CMSC" in text for text in texts)
