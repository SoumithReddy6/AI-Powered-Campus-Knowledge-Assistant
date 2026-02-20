from __future__ import annotations

import logging
import textwrap
import time
from dataclasses import asdict

from campus_assistant.data_models import QueryResult
from campus_assistant.llm import answer_with_domain_assistant
from campus_assistant.nlp.entity_extractor import CampusEntityExtractor
from campus_assistant.nlp.intent import IntentClassifier
from campus_assistant.nlp.query_normalizer import QueryNormalizer
from campus_assistant.retrieval.vector_index import VectorIndex
from campus_assistant.config import SETTINGS

logger = logging.getLogger(__name__)


class RAGPipeline:
    def __init__(self, index: VectorIndex) -> None:
        self.index = index
        self.intent_classifier = IntentClassifier()
        self.entity_extractor = CampusEntityExtractor()
        self.query_normalizer = QueryNormalizer()
        self.query_normalizer.bootstrap_from_documents(self.index.documents)

    def answer(self, query: str, top_k: int | None = None) -> QueryResult:
        start = time.perf_counter()

        normalized = self.query_normalizer.normalize(query)
        retrieval_query = normalized.corrected if normalized.corrected else query

        intent = self.intent_classifier.predict(retrieval_query)
        entities = self.entity_extractor.extract(retrieval_query)
        source_filter = _source_filter_for_intent(intent.label)
        retrieved = self.index.search(
            query=retrieval_query,
            top_k=top_k or SETTINGS.top_k,
            source_types=source_filter,
        )

        answer_text = self._generate_answer(
            query=retrieval_query,
            intent=intent.label,
            retrieved=retrieved,
            corrected_from_original=normalized.applied,
        )

        latency_ms = (time.perf_counter() - start) * 1000
        sources = [
            {
                "doc_id": doc.doc_id,
                "title": doc.title,
                "source_type": doc.source_type,
                "score": round(score, 4),
                "metadata": doc.metadata,
            }
            for doc, score in retrieved
        ]

        return QueryResult(
            query=query,
            answer=answer_text,
            intent=intent.label,
            entities=[asdict(entity) for entity in entities],
            sources=sources,
            latency_ms=round(latency_ms, 2),
            normalized_query=retrieval_query,
            correction_applied=normalized.applied,
            corrections=normalized.changes,
        )

    def _generate_answer(
        self,
        query: str,
        intent: str,
        retrieved: list[tuple],
        corrected_from_original: bool = False,
    ) -> str:
        context_lines = []
        for doc, score in retrieved:
            context_lines.append(f"- [{doc.source_type}] {doc.title} (score={score:.3f})")
            context_lines.append(textwrap.shorten(doc.text.replace("\n", " "), width=260, placeholder="..."))
        context = "\n".join(context_lines)

        llm_answer = _try_openai_answer(query=query, context=context)
        if llm_answer:
            return llm_answer

        if not retrieved:
            return (
                "I could not find supporting campus records for that question yet. "
                "Try rephrasing with course code, building name, or semester details."
            )

        snippets = []
        for doc, _ in retrieved[:3]:
            snippets.append(textwrap.shorten(doc.text.replace("\n", " "), width=220, placeholder="..."))

        prefix = ""
        if corrected_from_original:
            prefix = f'I interpreted your question as: "{query}".\n'

        return (
            prefix
            + f"Intent detected: {intent}. "
            f"Based on the most relevant UMBC records, here is what I found:\n"
            + "\n".join(f"{i+1}. {snippet}" for i, snippet in enumerate(snippets))
        )


def _source_filter_for_intent(intent: str) -> set[str] | None:
    mapping = {
        "event": {"event"},
        "class_schedule": {"class_schedule"},
        "time": {"calendar", "event", "class_schedule"},
        "location": {"event", "class_schedule"},
        "facility_hours": {"event", "calendar"},
    }
    return mapping.get(intent)


def _try_openai_answer(query: str, context: str) -> str | None:
    try:
        return answer_with_domain_assistant(
            query=query,
            context=context,
            route_label="rag_retrieval",
        )
    except Exception as exc:
        logger.warning("Domain assistant generation failed, using fallback answerer: %s", exc)
        return None
