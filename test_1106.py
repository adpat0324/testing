import os
from llama_index.core import Document
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader
from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever

# -----------------------------
# CONFIG
# -----------------------------

FILENAME = "Fee_Schedule.pdf"
FILEPATH = f"/mnt/data/{FILENAME}"

# Your existing stores
vector_store = RisklabVectorStore("kb_vector_store")
summary_store = RisklabVectorStore("kb_summary_store")


# -----------------------------
# DELETE OLD EMBEDDINGS
# -----------------------------

def delete_document_from_store(file_name: str):
    """Delete all vector + summary nodes belonging to a file."""
    
    # --- Vector nodes ---
    vindex = VectorStoreIndex.from_vector_store(vector_store)
    vretriever = VectorIndexRetriever(index=vindex, similarity_top_k=1000)
    
    vector_results = vretriever.retrieve("TextNode")  # known valid type

    deleted_v = 0
    for node in vector_results:
        if node.metadata.get("file_name") == file_name:
            vector_store.delete(node.node_id)
            deleted_v += 1

    # --- Summary nodes ---
    sindex = VectorStoreIndex.from_vector_store(summary_store)
    sretriever = VectorIndexRetriever(index=sindex, similarity_top_k=1000)
    
    summary_results = sretriever.retrieve("Document")  # summary nodes type

    deleted_s = 0
    for node in summary_results:
        if node.metadata.get("file_name") == file_name:
            summary_store.delete(node.node_id)
            deleted_s += 1

    print(f"✅ Deleted old embeddings for {file_name}: {deleted_v} vector, {deleted_s} summary")


# -----------------------------
# RE-ADD FILE
# -----------------------------

def readd_file(filepath: str):
    """Delete old embeddings and add new embeddings for a file."""
    
    file_name = os.path.basename(filepath)

    # ✅ Step 1: delete old embeddings
    delete_document_from_store(file_name)

    # ✅ Step 2: load + split
    docs = PDFReader(return_full_document=True).load_data(filepath)
    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)

    nodes = splitter.get_nodes_from_documents(docs)
    for node in nodes:
        node.metadata["file_name"] = file_name
        node.metadata["file_path"] = filepath

    # ✅ Step 3: embed + add new nodes
    vector_store.add(Settings.embed_model(nodes))
    print(f"🧠 Added {len(nodes)} new vector nodes for {file_name}")

    # ✅ Step 4: build fresh summaries
    def summarize_document(doc: Document):
        summary_prompt = f"Summarize in 5 concise sentences:\n\n{doc.text}"
        summary_text = Settings.llm.complete(summary_prompt)
        return Document(text=str(summary_text), metadata={"file_name": doc.metadata.get("file_name")})

    summary_docs = [summarize_document(d) for d in docs]
    summary_nodes = splitter.get_nodes_from_documents(summary_docs)

    for snode in summary_nodes:
        snode.metadata["file_name"] = file_name
        snode.metadata["file_path"] = filepath

    summary_store.add(Settings.embed_model(summary_nodes))
    print(f"🧾 Added {len(summary_nodes)} new summary nodes for {file_name}")


# -----------------------------
# ✅ RUN IT
# -----------------------------

readd_file(FILEPATH)
