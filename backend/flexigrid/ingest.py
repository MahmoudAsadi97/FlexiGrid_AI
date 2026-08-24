"""Corpus ingestion: load markdown documents, split into stable chunks.

Each corpus document carries a small front-matter header (id, title,
source_type, tags). Documents are split on level-2 headings; every section
becomes one retrieval chunk with a stable identifier ``<doc_id>#<n>`` so that
citations remain reproducible across runs and across corpus versions that do
not touch the section order.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

CORPUS_DIR = Path(__file__).resolve().parent / "corpus"

_FRONT_MATTER = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.DOTALL)


@dataclass(frozen=True)
class Chunk:
    chunk_id: str
    doc_id: str
    title: str          # document title
    section: str        # section heading
    text: str
    source_type: str
    tags: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "chunk_id": self.chunk_id,
            "doc_id": self.doc_id,
            "title": self.title,
            "section": self.section,
            "text": self.text,
            "source_type": self.source_type,
            "tags": list(self.tags),
        }


def _parse_front_matter(raw: str) -> tuple[dict[str, str], str]:
    match = _FRONT_MATTER.match(raw)
    if not match:
        return {}, raw
    meta: dict[str, str] = {}
    for line in match.group(1).splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip()] = value.strip()
    return meta, raw[match.end():]


def _split_sections(body: str) -> list[tuple[str, str]]:
    """Split a markdown body into (heading, text) pairs on '## ' headings."""
    sections: list[tuple[str, str]] = []
    heading = "Overview"
    lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if lines and "".join(lines).strip():
                sections.append((heading, "\n".join(lines).strip()))
            heading = line[3:].strip()
            lines = []
        else:
            lines.append(line)
    if lines and "".join(lines).strip():
        sections.append((heading, "\n".join(lines).strip()))
    return sections


def load_corpus(corpus_dir: Path | None = None) -> list[Chunk]:
    directory = corpus_dir or CORPUS_DIR
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        meta, body = _parse_front_matter(path.read_text(encoding="utf-8"))
        doc_id = meta.get("id", path.stem)
        title = meta.get("title", path.stem)
        source_type = meta.get("source_type", "unknown")
        tags = tuple(
            tag.strip().lower()
            for tag in meta.get("tags", "").split(",")
            if tag.strip()
        )
        for index, (section, text) in enumerate(_split_sections(body)):
            chunks.append(
                Chunk(
                    chunk_id=f"{doc_id}#{index}",
                    doc_id=doc_id,
                    title=title,
                    section=section,
                    text=text,
                    source_type=source_type,
                    tags=tags,
                )
            )
    if not chunks:
        raise RuntimeError(f"No corpus documents found in {directory}")
    return chunks


def corpus_fingerprint(chunks: list[Chunk]) -> str:
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk.chunk_id.encode())
        digest.update(chunk.text.encode())
    return digest.hexdigest()[:16]


if __name__ == "__main__":
    loaded = load_corpus()
    docs = sorted({chunk.doc_id for chunk in loaded})
    print(f"{len(loaded)} chunks from {len(docs)} documents "
          f"(fingerprint {corpus_fingerprint(loaded)})")
    for doc in docs:
        n = sum(1 for chunk in loaded if chunk.doc_id == doc)
        print(f"  {doc:<20} {n} chunks")
