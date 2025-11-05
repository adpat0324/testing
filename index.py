import os
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core import Settings, Document, VectorStoreIndex
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.readers import SimpleDirectoryReader
from llama_index.core.schema import NodeWithScore
from llama_index.core.schema import TextNode
from risklab.vectorstore.llamaindex import RisklabVectorStore

# -----------------------------------------------------------------------------
# 1️⃣ Configure Models and Risklab
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
# 2️⃣ IndexManager
# -----------------------------------------------------------------------------

class IndexManager:
    """Manages document ingestion, summarization, updates and deletion in RisklabVectorStore."""

    def __init__(self, use_streamlit: bool = True):
        self.logger = print
        self._deletion_lock = threading.Lock()

        # --- Connect to Risklab remote stores ---
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

        self.logger("✅ Initialized IndexManager using RisklabVectorStore backend")

    # -----------------------------------------------------------------------------
    # 3️⃣ Knowledge Base Loaders (multi-format)
    # -----------------------------------------------------------------------------

    def _read_kb_docs(self, kb_dir: Path) -> List[Document]:
        """Load all files in a knowledge base directory into LlamaIndex Document objects."""
        if not any(kb_dir.iterdir()):
            self.logger("⚠️ No files found in knowledge base directory.")
            return []

        self.logger(f"📂 Reading documents from {kb_dir}")
        reader = SimpleDirectoryReader(
            input_dir=str(kb_dir),
            recursive=True,
            required_exts=[".pdf", ".pptx", ".docx", ".xlsx", ".txt", ".pkl"],
        )
        return reader.load_data()

    def _group_documents(self, kb_docs: List[Document]) -> Dict[str, List[Document]]:
        """Group documents by file path."""
        grouped: Dict[str, List[Document]] = {}
        for doc in kb_docs:
            file_path = doc.metadata.get("file_path", "unknown")
            grouped.setdefault(file_path, []).append(doc)
        return grouped

    # -----------------------------------------------------------------------------
    # 4️⃣ Summary Generation
    # -----------------------------------------------------------------------------

    def _generate_document_summary(self, nodes: List[Document], doc_name: str) -> str:
        """Use LLM to summarize a set of nodes."""
        summary_prompt = (
            f"Produce a concise and comprehensive summary for {doc_name}. "
            f"Summarize main themes, findings, and key takeaways in ≤150 words:\n\n"
            + "\n".join([n.text for n in nodes[:5]])
        )
        try:
            result = Settings.llm.complete(summary_prompt)
            return str(result)
        except Exception as e:
            self.logger(f"⚠️ Failed to summarize {doc_name}: {e}")
            return "No summary available."

    # -----------------------------------------------------------------------------
    # 5️⃣ Prepare Nodes for Indexing
    # -----------------------------------------------------------------------------

    def _prepare_nodes(self, docs: List[Document], doc_name: str) -> Tuple[List[TextNode], str]:
        """Chunk and summarize a document, returning text nodes + summary."""
        try:
            splitter = SemanticSplitterNodeParser(buffer_size=3, breakpoint_percentile_threshold=85)
            nodes = splitter.get_nodes_from_documents(docs)
        except Exception:
            splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
            nodes = splitter.get_nodes_from_documents(docs)

        summary = self._generate_document_summary(nodes, doc_name)
        for node in nodes:
            node.metadata["file_name"] = os.path.basename(doc_name)
            node.metadata["file_path"] = doc_name
            node.metadata["document_summary"] = summary
        return nodes, summary

    # -----------------------------------------------------------------------------
    # 6️⃣ Core Index Operations
    # -----------------------------------------------------------------------------

    def index_documents(self, kb_dir: Path, parallel: bool = True, max_workers: int = 4):
        """Index all documents in a directory into Risklab stores."""
        kb_docs = self._read_kb_docs(kb_dir)
        grouped_docs = self._group_documents(kb_docs)
        if not grouped_docs:
            self.logger("⚠️ No documents found to index.")
            return

        tasks = list(grouped_docs.items())
        if parallel:
            with ThreadPoolExecutor(max_workers=max_workers) as ex:
                futures = {ex.submit(self._index_single, name, docs): name for name, docs in tasks}
                for f in as_completed(futures):
                    name = futures[f]
                    try:
                        f.result()
                        self.logger(f"✅ Indexed {name}")
                    except Exception as e:
                        self.logger(f"❌ Failed indexing {name}: {e}")
        else:
            for name, docs in tasks:
                self._index_single(name, docs)

    def _index_single(self, doc_name: str, docs: List[Document]):
        """Index one document (vector + summary embeddings)."""
        self.logger(f"📄 Indexing {doc_name}")
        nodes, summary = self._prepare_nodes(docs, doc_name)

        # Main embeddings
        embedded_nodes = Settings.embed_model(nodes)
        self.vector_store.add(embedded_nodes)
        self.logger(f"✅ Added {len(embedded_nodes)} nodes to vector store")

        # Summary embeddings
        summary_doc = Document(text=summary, metadata={"file_name": os.path.basename(doc_name)})
        summary_nodes = [summary_doc]
        embedded_summary = Settings.embed_model(summary_nodes)
        self.summary_store.add(embedded_summary)
        self.logger(f"✅ Added summary for {doc_name}")

    def update_document(self, file_path: str):
        """Re-index an existing document by deleting and re-adding."""
        file_name = os.path.basename(file_path)
        self.delete_document(file_name)
        kb_docs = self._read_kb_docs(Path(file_path).parent)
        docs = [d for d in kb_docs if d.metadata.get("file_name") == file_name]
        if docs:
            self._index_single(file_name, docs)
        else:
            self.logger(f"⚠️ File {file_name} not found for update.")

    def delete_document(self, file_name: str):
        """Delete embeddings from both stores for a given file."""
        self.logger(f"🗑️ Deleting '{file_name}'")
        with self._deletion_lock:
            vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
            summary_index = VectorStoreIndex.from_vector_store(self.summary_store)
            vec_retr = VectorIndexRetriever(index=vector_index, similarity_top_k=50)
            sum_retr = VectorIndexRetriever(index=summary_index, similarity_top_k=50)
            vec_matches = vec_retr.retrieve(file_name)
            sum_matches = sum_retr.retrieve(file_name)

            for m in vec_matches:
                try:
                    self.vector_store.delete(ref_doc_id=m.node.id_)
                except Exception as e:
                    self.logger(f"⚠️ Could not delete vector node: {e}")

            for m in sum_matches:
                try:
                    self.summary_store.delete(ref_doc_id=m.node.id_)
                except Exception as e:
                    self.logger(f"⚠️ Could not delete summary node: {e}")

            self.logger(f"✅ Deleted {len(vec_matches)} vectors and {len(sum_matches)} summaries")

    # -----------------------------------------------------------------------------
    # 7️⃣ Query
    # -----------------------------------------------------------------------------

    def query(self, text: str, top_k: int = 3):
        """Query vector and summary indices."""
        v_idx = VectorStoreIndex.from_vector_store(self.vector_store)
        s_idx = VectorStoreIndex.from_vector_store(self.summary_store)

        v_retr = VectorIndexRetriever(index=v_idx, similarity_top_k=top_k)
        s_retr = VectorIndexRetriever(index=s_idx, similarity_top_k=2)

        v_results = v_retr.retrieve(text)
        s_results = s_retr.retrieve(text)

        self.logger("🔍 Vector Results:")
        for r in v_results:
            self.logger(f"• {r.metadata.get('file_name')} | score={r.score:.3f}")
        self.logger("🧾 Summary Results:")
        for r in s_results:
            self.logger(f"• {r.metadata.get('file_name')} | score={r.score:.3f}")
        return v_results, s_results


# -----------------------------------------------------------------------------
# 8️⃣ Example Run
# -----------------------------------------------------------------------------

if __name__ == "__main__":
    kb_path = Path("/mnt/data/knowledge_base")
    manager = IndexManager()
    manager.index_documents(kb_path)
    manager.query("What does the document say about MLOps governance?")

