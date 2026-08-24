"""Corpus ingestion and hybrid retrieval."""

import unittest

from tests import helpers

from flexigrid.embeddings import OllamaEmbeddings, TfidfEmbeddings
from flexigrid.ingest import corpus_fingerprint, load_corpus
from flexigrid.retrieval import RetrievalIndex, get_index


class IngestTests(unittest.TestCase):
    def test_corpus_loads_with_unique_stable_ids(self):
        chunks = load_corpus()
        self.assertGreaterEqual(len(chunks), 40)
        ids = [chunk.chunk_id for chunk in chunks]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertTrue(all("#" in chunk_id for chunk_id in ids))

    def test_every_document_has_front_matter(self):
        for chunk in load_corpus():
            self.assertNotEqual(chunk.source_type, "unknown",
                                f"{chunk.doc_id} lacks source_type")
            self.assertTrue(chunk.tags, f"{chunk.doc_id} lacks tags")

    def test_fingerprint_is_stable(self):
        self.assertEqual(corpus_fingerprint(load_corpus()),
                         corpus_fingerprint(load_corpus()))


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = get_index()

    def test_bm25_ranks_ev_manual_first_for_ev_query(self):
        results = self.index.retrieve("charge the EV in eco mode", mode="bm25")
        self.assertEqual(results[0]["doc_id"], "manual-ev")

    def test_dense_ranks_ev_manual_first_for_ev_query(self):
        results = self.index.retrieve("charge the electric car battery",
                                      mode="dense")
        self.assertEqual(results[0]["doc_id"], "manual-ev")

    def test_hybrid_returns_requested_depth_with_scores(self):
        results = self.index.retrieve("Elia wind forecast", top_k=4,
                                      mode="hybrid")
        self.assertEqual(len(results), 4)
        for row in results:
            self.assertIn("bm25", row["scores"])
            self.assertIn("dense", row["scores"])
            self.assertIsNotNone(row["scores"]["bm25"])
            self.assertIsNotNone(row["scores"]["dense"])

    def test_retrieval_is_deterministic(self):
        first = self.index.retrieve("capacity tariff peak", mode="hybrid")
        second = self.index.retrieve("capacity tariff peak", mode="hybrid")
        self.assertEqual(first, second)

    def test_top_k_is_clamped(self):
        self.assertEqual(len(self.index.retrieve("grid", top_k=99)), 8)
        self.assertEqual(len(self.index.retrieve("grid", top_k=-3)), 1)

    def test_unknown_mode_raises(self):
        with self.assertRaises(ValueError):
            self.index.retrieve("grid", mode="quantum")

    def test_capacity_query_finds_capacity_policy(self):
        results = self.index.retrieve(
            "why is household load capped at 4.6 kW", mode="hybrid")
        self.assertIn("policy-capacity", [row["doc_id"] for row in results])


class EmbeddingBackendTests(unittest.TestCase):
    def test_tfidf_backend_is_deterministic_and_normalized(self):
        texts = [f"{c.title}. {c.text}" for c in load_corpus()]
        backend = TfidfEmbeddings(texts)
        first = backend.embed(["charge the EV"])[0]
        second = backend.embed(["charge the EV"])[0]
        self.assertEqual(first, second)
        norm = sum(value * value for value in first) ** 0.5
        self.assertAlmostEqual(norm, 1.0, places=5)

    def test_ollama_backend_against_mock_endpoint(self):
        base_url = helpers.start_mock_llm()
        backend = OllamaEmbeddings(base_url=base_url, model="mock-embed")
        vectors = backend.embed(["wind forecast", "wind forecast", "dishwasher"])
        self.assertEqual(vectors[0], vectors[1])
        self.assertNotEqual(vectors[0], vectors[2])

    def test_dense_index_with_mock_ollama_backend(self):
        base_url = helpers.start_mock_llm()
        index = RetrievalIndex(embedding_preference="tfidf")
        # construct a dedicated index against the mock explicitly
        index._backend = OllamaEmbeddings(base_url=base_url, model="mock-embed")
        results = index.retrieve("EV charger eco mode", mode="dense")
        self.assertEqual(len(results), 4)


if __name__ == "__main__":
    unittest.main()
