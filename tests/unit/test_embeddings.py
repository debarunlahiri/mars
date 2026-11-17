import numpy as np

from mars.schemas import Report, Source
from mars.storage import chunks_from_report
from mars.storage.embeddings import HashEmbedder


async def test_hash_embedder_is_deterministic_unit_length_and_lexically_ranked():
    e = HashEmbedder(256)
    a, b, c = await e.embed(
        [
            "hybrid retrieval improves recall over dense retrieval",
            "hybrid retrieval improves recall",
            "the weather in lisbon is sunny today",
        ]
    )
    again = (await e.embed(["hybrid retrieval improves recall"]))[0]
    assert np.allclose(b, again)
    assert abs(np.linalg.norm(a) - 1) < 1e-5
    assert float(a @ b) > float(a @ c) + 0.3


def test_chunks_come_from_verified_quotes_only_and_are_deduped():
    r = Report(
        question="q",
        status="complete",
        markdown="m",
        sources=[
            Source(id=1, title="A", url="https://a.com", quotes=["quote one", "quote one", " "]),
            Source(id=2, title="B", url="https://b.com", snippet="unverified snippet", quotes=[]),
        ],
    )
    chunks = chunks_from_report(r)
    assert [(c.url, c.text) for c in chunks] == [("https://a.com", "quote one")]
