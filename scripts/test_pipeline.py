from app.services.embedding_service import embed_texts
from app.services.vector_store import get_client, insert_chunks, search_by_vector, get_stats

# 1. Embedding
texts = [
    'Kubernetes Pod CrashLoopBackOff oomkilled',
    'Redis connection pool exhaustion causes cascade failure',
    'MySQL slow query spikes CPU usage'
]
embs = embed_texts(texts)
print(f'Embeddings: {len(embs)} vectors, dim={len(embs[0])}')

# 2. Insert into Milvus
chunks = [{
    'document_id': 999, 'chunk_index': i, 'content': t, 'embedding': e,
    'tags': 'test', 'asset_type': 'container', 'severity': 'warning',
    'source_type': 'test', 'doc_title': 'Test Doc'
} for i, (t, e) in enumerate(zip(texts, embs))]
insert_chunks(chunks)
print(f'After insert: {get_stats()}')

# 3. Search
q_emb = embed_texts(['Pod restart too many times'])[0]
results = search_by_vector(q_emb, top_k=2)
print(f'Search results: {len(results)} hits')
for r in results:
    print(f"  score={r['score']} content={r['content'][:60]}")
