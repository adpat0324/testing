import os
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core import Document, Settings, VectorStoreIndex
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.schema import NodeWithScore
from llama_index.readers.file import PDFReader
from risklab.vectorstore.llamaindex import RisklabVectorStore

# -----------------------------------------------------------------------------
# 1️⃣ Azure + LlamaIndex Settings
# -----------------------------------------------------------------------------

Settings.embed_model = AzureOpenAIEmbedding(
    engine="text-embedding-3-small",
    azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential()),
    azure_endpoint="https://cognitiveservices.azure.com/.default",
)

Settings.llm = AzureOpenAI(
    engine="gpt-4o",
    azure_ad_token_provider=get_bearer_token_provider(DefaultAzureCredential()),
    azure_endpoint="https://cognitiveservices.azure.com/.default",
)

# -----------------------------------------------------------------------------
# 2️⃣ Index Manager
# -----------------------------------------------------------------------------

class IndexManager:
    """Manager for indexing, updating, summarizing and deleting documents in Risklab VectorStore."""

    def __init__(self, use_streamlit: bool = True):
        self.logger = print  # Replace with streamlit logger if applicable
        self._deletion_lock = threading.Lock()

        # --- Risklab remote stores (no local cache) ---
        self.vector_store = RisklabVectorStore(
            api_key=os.getenv("RISKLAB_OPEN_AI_KEY"),
            namespace="uga-ai",
            collection_name="vector-store",
        )
        self.summary_store = RisklabVectorStore(
            api_key=os.getenv("RISKLAB_OPEN_AI_KEY"),
            namespace="uga-ai",
            collection_name="summary-store",
        )

        self.vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
        self.summary_index = VectorStoreIndex.from_vector_store(self.summary_store)

        self.logger(f"✅ Initialized IndexManager using RisklabVectorStore.")

    # -----------------------------------------------------------------------------
    # 3️⃣ Document Ingestion and Embedding
    # -----------------------------------------------------------------------------

    def _load_pdf(self, file_path: str) -> List[Document]:
        docs = PDFReader(return_full_document=True).load_data(file_path)
        for d in docs:
            d.metadata["file_path"] = file_path
            d.metadata["file_name"] = os.path.basename(file_path)
        return docs

    def _chunk_documents(self, docs: List[Document]) -> List[Document]:
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)
        return splitter.get_nodes_from_documents(docs)

    def _summarize_document(self, docs: List[Document]) -> List[Document]:
        summarized = []
        for doc in docs:
            prompt = f"Summarize this document in 5 concise sentences:\n\n{doc.text}"
            try:
                summary = Settings.llm.complete(prompt)
                summarized.append(Document(text=str(summary), metadata=doc.metadata))
            except Exception as e:
                self.logger(f"⚠️ Failed to summarize {doc.metadata.get('file_name')}: {e}")
        return summarized

    # -----------------------------------------------------------------------------
    # 4️⃣ Index Document
    # -----------------------------------------------------------------------------

    def index_document(self, file_path: str):
        """Index a new document into Risklab vector and summary collections."""
        self.logger(f"📄 Indexing document: {file_path}")
        docs = self._load_pdf(file_path)
        nodes = self._chunk_documents(docs)

        # --- Main embeddings ---
        embedded_nodes = Settings.embed_model(nodes)
        self.vector_store.add(embedded_nodes)
        self.logger(f"✅ Stored {len(embedded_nodes)} nodes in vector-store")

        # --- Summary embeddings ---
        summary_docs = self._summarize_document(docs)
        summary_nodes = self._chunk_documents(summary_docs)
        embedded_summaries = Settings.embed_model(summary_nodes)
        self.summary_store.add(embedded_summaries)
        self.logger(f"✅ Stored {len(embedded_summaries)} summaries in summary-store")

    # -----------------------------------------------------------------------------
    # 5️⃣ Delete Document
    # -----------------------------------------------------------------------------

    def delete_document(self, file_name: str):
        """Delete all embeddings for a given document from both stores."""
        self.logger(f"🗑️ Deleting document '{file_name}'")

        with self._deletion_lock:
            vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
            summary_index = VectorStoreIndex.from_vector_store(self.summary_store)

            vector_retriever = VectorIndexRetriever(index=vector_index, similarity_top_k=50)
            summary_retriever = VectorIndexRetriever(index=summary_index, similarity_top_k=50)

            vector_results = vector_retriever.retrieve(file_name)
            summary_results = summary_retriever.retrieve(file_name)

            deleted_vec = 0
            deleted_sum = 0

            for r in vector_results:
                try:
                    self.vector_store.delete(ref_doc_id=r.node.id_)
                    deleted_vec += 1
                except Exception as e:
                    self.logger(f"⚠️ Failed to delete vector node {r.node.id_}: {e}")

            for r in summary_results:
                try:
                    self.summary_store.delete(ref_doc_id=r.node.id_)
                    deleted_sum += 1
                except Exception as e:
                    self.logger(f"⚠️ Failed to delete summary node {r.node.id_}: {e}")

            self.logger(f"✅ Deleted {deleted_vec} vector nodes and {deleted_sum} summaries for '{file_name}'")

    # -----------------------------------------------------------------------------
    # 6️⃣ Update Document
    # -----------------------------------------------------------------------------

    def update_document(self, file_path: str):
        """Delete existing embeddings for a file, then re-index."""
        file_name = os.path.basename(file_path)
        self.logger(f"🔁 Updating document: {file_name}")
        self.delete_document(file_name)
        self.index_document(file_path)

    # -----------------------------------------------------------------------------
    # 7️⃣ Retrieve
    # -----------------------------------------------------------------------------

    def query(self, text: str, top_k: int = 3):
        """Query both vector and summary indices."""
        vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
        summary_index = VectorStoreIndex.from_vector_store(self.summary_store)

        v_retriever = VectorIndexRetriever(index=vector_index, similarity_top_k=top_k)
        s_retriever = VectorIndexRetriever(index=summary_index, similarity_top_k=2)

        v_results = v_retriever.retrieve(text)
        s_results = s_retriever.retrieve(text)

        self.logger("🔍 Vector Results:")
        for r in v_results:
            self.logger(f"• {r.metadata.get('file_name')} | score={r.score:.3f}")
            self.logger(r.text[:200])

        self.logger("🧾 Summary Results:")
        for r in s_results:
            self.logger(f"• {r.metadata.get('file_name')} | score={r.score:.3f}")
            self.logger(r.text[:200])

        return v_results, s_results

    # -----------------------------------------------------------------------------
    # 8️⃣ Parallel Indexing
    # -----------------------------------------------------------------------------

    def index_documents_parallel(self, files: List[str], max_workers: int = 4):
        """Index multiple PDFs concurrently."""
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(self.index_document, f): f for f in files}
            for fut in as_completed(futures):
                file_name = futures[fut]
                try:
                    fut.result()
                    self.logger(f"✅ Finished indexing {file_name}")
                except Exception as e:
                    self.logger(f"❌ Error indexing {file_name}: {e}")


# -----------------------------------------------------------------------------
# 9️⃣ Example Run
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    manager = IndexManager()
    test_pdf = "/mnt/data/demo.pdf"

    # Index
    manager.index_document(test_pdf)

    # Query
    manager.query("What does the document say about governance in MLOps?")

    # Update
    manager.update_document(test_pdf)

    # Delete
    manager.delete_document(os.path.basename(test_pdf))
