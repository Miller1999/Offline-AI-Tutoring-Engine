"""Tests for the ChromaDB backed learning service."""

from app.services import learning
from tests.conftest import FakeCollection


class TestCategories:
    """Categories are counted over the whole collection, not over a sample."""

    def test_counts_every_chunk(self, fake_collection: FakeCollection) -> None:
        categories = learning.get_categories()

        counts = {item["categoria"]: item["total"] for item in categories}

        assert counts == {"library": 2, "tutorial": 1}

    def test_categories_are_sorted(self, fake_collection: FakeCollection) -> None:
        categories = learning.get_categories()

        assert [item["categoria"] for item in categories] == ["library", "tutorial"]

    def test_result_is_memoised(self, fake_collection: FakeCollection) -> None:
        learning.get_categories()
        calls_after_first = fake_collection.get_calls
        learning.get_categories()

        assert fake_collection.get_calls == calls_after_first

    def test_cache_is_dropped_on_request(self, fake_collection: FakeCollection) -> None:
        learning.get_categories()
        calls_after_first = fake_collection.get_calls

        learning.reset_cache()
        learning.get_categories()

        assert fake_collection.get_calls > calls_after_first

    def test_empty_collection_returns_no_categories(self) -> None:
        assert learning.get_categories() == []


class TestTopics:
    """Topics are grouped inside their category."""

    def test_topics_of_a_category(self, fake_collection: FakeCollection) -> None:
        topics = learning.get_topics_by_category("library")

        assert len(topics) == 1
        assert topics[0]["tema"] == "Data Structures"
        assert topics[0]["total_chunks"] == 2

    def test_sections_are_collected(self, fake_collection: FakeCollection) -> None:
        topics = learning.get_topics_by_category("library")

        assert topics[0]["secciones"] == ["dicts", "lists"]

    def test_unknown_category_returns_no_topics(self, fake_collection: FakeCollection) -> None:
        assert learning.get_topics_by_category("does-not-exist") == []


class TestContent:
    """The content of a topic is returned chunk by chunk."""

    def test_content_of_a_topic(self, fake_collection: FakeCollection) -> None:
        content = learning.get_content_by_topic("Data Structures")

        assert len(content) == 2
        assert content[0]["seccion"] == "lists"

    def test_content_can_be_filtered_by_category(self, fake_collection: FakeCollection) -> None:
        content = learning.get_content_by_topic("Data Structures", "tutorial")

        assert content == []


class TestSearch:
    """Semantic search returns a relevance score per result."""

    def test_results_carry_a_relevance_score(self, fake_collection: FakeCollection) -> None:
        results = learning.search("lists")

        assert len(results) == 3
        assert results[0]["relevancia"] == 75

    def test_results_carry_their_source(self, fake_collection: FakeCollection) -> None:
        results = learning.search("lists")

        assert results[0]["fuente"] == "library/list.txt"


class TestStats:
    """Statistics summarise the knowledge base."""

    def test_stats_of_a_populated_collection(self, fake_collection: FakeCollection) -> None:
        stats = learning.get_stats()

        assert stats["conectado"] is True
        assert stats["total_chunks"] == 3
        assert stats["total_categorias"] == 2

    def test_stats_without_a_vector_store(self) -> None:
        stats = learning.get_stats()

        assert stats["conectado"] is False
        assert stats["total_chunks"] == 0
