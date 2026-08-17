from app.config import BASE_DIR, CHUNK_DROP_TOKENS
from app.ingestion.parsers import parse_document
from app.ingestion.chunker import chunk_document
from app.ingestion.aware_parser import parse_and_chunk_aware_pdf
from app.ingestion.hearts_parser import parse_and_chunk_hearts_pdf
from app.embeddings.embedder import embed_texts, count_tokens
from app.embeddings.vector_store import add_chunks_to_store, list_all_documents

SEED_DIR = BASE_DIR / "data" / "seed_documents"

SEED_DOCUMENTS = [
    {
        "document_id": "seed_polypharmacy_guide",
        "filename": "Polypharmacy in Older People (AWTTC, 2023).pdf",
        # NOTE: file on disk has a double extension (saved as
        # "polypharmacy_guide.pdf.pdf") — matching that here so this seed
        # actually resolves and loads instead of silently being skipped.
        "file_path": SEED_DIR / "polypharmacy_guide.pdf.pdf",
        "parser": "generic",
        "source_url": "https://awttc.nhs.wales/",
    },
    {
        "document_id": "seed_who_aware_antibiotic_book",
        "filename": "WHO AWaRe Antibiotic Book - Web Annex: Infographics (WHO/MHP/HPS/EML/2022.02)",
        "file_path": SEED_DIR / "WhoAware.pdf",
        "parser": "aware",
        "source_url": "https://iris.who.int/handle/10665/365135",
        # Lower than the default CHUNK_DROP_TOKENS: this document's own
        # sections are legitimately terse ("Imaging: Usually not needed" is
        # a complete, useful answer, not extraction noise like the other two
        # documents' short chunks tend to be). 20 tokens still catches real
        # noise (stray page numbers, single characters) without discarding
        # real short clinical answers.
        "drop_tokens": 20,
    },
    {
        "document_id": "seed_who_hearts_protocols",
        "filename": "HEARTS Technical Package: Evidence-based Treatment Protocols (WHO/NMH/NVI/18.2)",
        "file_path": SEED_DIR / "WhoHearts.pdf",
        "parser": "hearts",
        "source_url": "https://iris.who.int/handle/10665/260421",
    },
]

PARSERS = {
    "aware": lambda path: parse_and_chunk_aware_pdf(str(path)),
    "hearts": lambda path: parse_and_chunk_hearts_pdf(str(path)),
    "generic": lambda path: chunk_document(parse_document(str(path))),
}


def ensure_seed_documents_loaded():
    """
    Runs once at backend startup. Ensures the core reference guideline(s)
    are always indexed, so the app has a working knowledge base without
    requiring a manual upload every session.
    """
    existing_ids = {doc["document_id"] for doc in list_all_documents()}

    for seed in SEED_DOCUMENTS:
        if seed["document_id"] in existing_ids:
            print(f"[seed] '{seed['filename']}' already indexed, skipping.")
            continue

        if not seed["file_path"].exists():
            print(f"[seed] WARNING: seed file not found at {seed['file_path']}, skipping.")
            continue

        print(f"[seed] Ingesting '{seed['filename']}'...")

        # Section-aware parsing per document type: AWaRe and HEARTS have
        # non-linear infographic layouts that need dedicated parsers (see
        # app/ingestion/aware_parser.py and hearts_parser.py for why); the
        # Polypharmacy guide and any future generic upload use the shared
        # heading-aware, token-budgeted chunker.
        chunks = PARSERS[seed.get("parser", "generic")](seed["file_path"])

        # Chunks under the drop threshold are extraction noise (e.g. a lone
        # short line with no useful content) rather than real chunks — drop
        # them before they're embedded and stored. Most documents use the
        # shared CHUNK_DROP_TOKENS default; a seed can override with its own
        # "drop_tokens" when its real content is legitimately terse.
        drop_threshold = seed.get("drop_tokens", CHUNK_DROP_TOKENS)
        before = len(chunks)
        chunks = [c for c in chunks if count_tokens(c["text"]) >= drop_threshold]
        dropped = before - len(chunks)
        if dropped:
            print(f"[seed] Dropped {dropped} chunk(s) under {drop_threshold} tokens (noise).")

        if not chunks:
            print(f"[seed] WARNING: '{seed['filename']}' produced no chunks, skipping.")
            continue

        texts = [c["text"] for c in chunks]
        embeddings = embed_texts(texts)
        add_chunks_to_store(
            chunks,
            embeddings,
            document_id=seed["document_id"],
            filename=seed["filename"],
            source_url=seed.get("source_url"),
        )
        print(f"[seed] Done — {len(chunks)} chunks indexed.")
