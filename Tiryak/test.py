import time
from app.api.routes_summary import get_all_chunks_for_document
from app.advanced.summarizer import summarize_document

document_id = "2dc947c4-5f6a-489e-af94-9e03055935ab"

chunks = get_all_chunks_for_document(document_id)
print(f"Number of chunks: {len(chunks)}")

start = time.time()
result = summarize_document(chunks, batch_size=6)
print(f"Took {time.time() - start:.1f} seconds")
print(f"Number of API calls made: {len(result['chunk_summaries']) + 1}")