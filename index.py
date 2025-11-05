import os
import pickle
import threading
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from llama_index.embeddings.azure_openai import AzureOpenAIEmbedding
from llama_index.llms.azure_openai import AzureOpenAI
from llama_index.core import Settings, VectorStoreIndex
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.vector_stores import MetadataFilter, MetadataFilters, VectorStoreQuery
from llama_index.readers import SimpleDirectoryReader
from llama_index.core.schema import Document as LlamaIndexDocument
from risklab.vectorstore.llamaindex import RisklabVectorStore

RISKLAB_OPEN_AI_KEY = os.getenv("RISKLAB_OPEN_AI_KEY")

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


class IndexManager:
    def __init__(self, use_streamlit: bool = True):
        self.logger = print
        self._deletion_lock = threading.Lock()

        self.vector_store = RisklabVectorStore(
            api_key=RISKLAB_OPEN_AI_KEY, namespace="uga-ai", collection_name="vector-store"
        )
        self.summary_store = RisklabVectorStore(
            api_key=RISKLAB_OPEN_AI_KEY, namespace="uga-ai", collection_name="summary-store"
        )

        self.vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
        self.summary_index = VectorStoreIndex.from_vector_store(self.summary_store)
        self._load_index_cache: Dict[str, Tuple[VectorStoreIndex, VectorStoreIndex]] = {}

    # 1️⃣
    def _load_or_create_index(self, index_cache: Path, vector: bool = True):
        return (VectorStoreIndex.from_vector_store(self.vector_store)
                if vector else
                VectorStoreIndex.from_vector_store(self.summary_store))

    # 2️⃣
    def _read_kb_docs(self, kb_dir: Path) -> List[LlamaIndexDocument]:
        if not any(kb_dir.iterdir()):
            self.logger("No files to index.")
            return []
        return SimpleDirectoryReader(
            input_dir=str(kb_dir),
            recursive=True,
            required_exts=[".pdf", ".pptx", ".docx", ".xlsx", ".txt", ".pkl"],
        ).load_data()

    # 3️⃣
    def _group_documents(self, kb_docs: List[LlamaIndexDocument]) -> Dict[str, List[LlamaIndexDocument]]:
        out: Dict[str, List[LlamaIndexDocument]] = {}
        for doc in kb_docs:
            fp = doc.metadata.get("file_path", "unknown")
            out.setdefault(fp, []).append(doc)
        return out

    # 4️⃣
    def _get_file_hash_from_store(self, doc_name: str) -> Optional[str]:
        filters = MetadataFilters(filters=[MetadataFilter(key="file_path", value=doc_name)])
        try:
            result = self.vector_store.query(VectorStoreQuery(filters=filters, similarity_top_k=1))
            if result and result.nodes:
                return result.nodes[0].metadata.get("file_hash")
        except Exception:
            pass
        return None

    def _build_tasks(self, documents: Dict[str, List[LlamaIndexDocument]], streamlit_off: bool=False):
        tasks = []
        for doc_name, docs in documents.items():
            incoming_hash = docs[0].metadata.get("file_hash")
            existing_hash = self._get_file_hash_from_store(doc_name)
            if not existing_hash:
                tasks.append((doc_name, docs, "new", streamlit_off))
            elif existing_hash != incoming_hash:
                tasks.append((doc_name, docs, "overwrite", streamlit_off))
            else:
                self.logger(f"Skipping {doc_name}, unchanged.")
        return tasks

    # 5️⃣
    def _safe_delete_document_nodes(self, doc_name_spaces: str):
        with self._deletion_lock:
            try:
                v_idx = VectorStoreIndex.from_vector_store(self.vector_store)
                v_retr = VectorIndexRetriever(index=v_idx, similarity_top_k=100)
                v_hits = v_retr.retrieve(doc_name_spaces)
                for h in v_hits:
                    try:
                        self.vector_store.delete(ref_doc_id=h.node.id_)
                    except Exception as e:
                        self.logger(f"Failed to delete vector node: {e}")

                s_idx = VectorStoreIndex.from_vector_store(self.summary_store)
                s_retr = VectorIndexRetriever(index=s_idx, similarity_top_k=100)
                s_hits = s_retr.retrieve(doc_name_spaces)
                for h in s_hits:
                    try:
                        self.summary_store.delete(ref_doc_id=h.node.id_)
                    except Exception as e:
                        self.logger.warbubg(f"Failed to delete summary node: {e}", streamlit_off=True)

                if not v_hits and not s_hits:
                    self.logger.info(f"No existing nodes found for '{doc_name_spaces}'.", streamlit_off=True)
            except Exception as e:
                self.logger.error(f"Unexpected deletion error: {e}", streamlit_off=True)
                raise

    # 6️⃣
    def _prepare_nodes(self, task: Tuple[str, List[LlamaIndexDocument], str, bool]):
        doc_name, docs, action, streamlit_off = task
        doc_name_spaces = doc_name.replace("_", " ")
        if action == "overwrite":
            self.logger(f"Re-indexing {doc_name_spaces}...")
            self._safe_delete_document_nodes(doc_name_spaces)

        try:
            splitter = SemanticSplitterNodeParser(buffer_size=3, breakpoint_percentile_threshold=85)
            nodes = splitter.get_nodes_from_documents(docs)
        except Exception:
            splitter = SentenceSplitter(chunk_size=1024, chunk_overlap=200)
            nodes = splitter.get_nodes_from_documents(docs)

        summary = self._generate_document_summary(nodes, doc_name_spaces)
        for node in nodes:
            node.metadata.update({
                "document_summary": summary,
                "file_name": os.path.basename(doc_name),
                "file_path": doc_name,
            })

        embedded_nodes = Settings.embed_model(nodes)
        self.vector_store.add(embedded_nodes)

        summary_doc = LlamaIndexDocument(text=summary, metadata={"file_name": os.path.basename(doc_name), "file_path": doc_name})
        embedded_summary = Settings.embed_model([summary_doc])
        self.summary_store.add(embedded_summary)

        return (doc_name, nodes, action, streamlit_off)

    # 7️⃣
    def persist_indices(self):
        self.logger("Indices persisted remotely to RisklabVectorStore (no local cache).")

    # 8️⃣
    def _generate_document_summary(self, nodes: List, doc_name: str) -> str:
        summary_prompt = (
            "Produce a concise and comprehensive summary description. "
            "Start with 10–25 words describing the document type and purpose. "
            "Aim for 50–150 words total."
        )
        try:
            from llama_index.core import SummaryIndex
            query_engine = SummaryIndex(nodes).as_query_engine()
            return str(query_engine.query(summary_prompt))
        except Exception:
            try:
                return str(Settings.llm.complete(summary_prompt + "\n\n" + "\n".join(n.text for n in nodes[:5])))
            except Exception:
                return "No summary."

    # 9️⃣
    def update_index(self, kb_dir: Path, parallel: bool=True, max_workers: Optional[int]=None, streamlit_off: bool=False):
        kb_docs = self._read_kb_docs(kb_dir)
        if not kb_docs:
            self.logger("Nothing to index.")
            return
        documents = self._group_documents(kb_docs)
        tasks = self._build_tasks(documents, streamlit_off=streamlit_off)

        if parallel and tasks:
            max_workers = max_workers or min(8, os.cpu_count() or 4)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = [executor.submit(self._prepare_nodes, t) for t in tasks]
                for f in as_completed(futures):
                    _ = f.result()
        else:
            for t in tasks:
                self._prepare_nodes(t)
        self.logger(f"Indexed {len(tasks)} documents successfully.")

    # 🔟
    def load_index(self, files_sel: List[str] = []) -> Dict[str, Tuple[VectorStoreIndex, VectorStoreIndex]]:
        selection = set(files_sel) if files_sel else None
        index: Dict[str, Tuple[VectorStoreIndex, VectorStoreIndex]] = {}
        doc_names = selection or {"*"}
        for doc_name in doc_names:
            if doc_name in self._load_index_cache:
                index[doc_name] = self._load_index_cache[doc_name]
                continue
            v_idx = VectorStoreIndex.from_vector_store(self.vector_store)
            s_idx = VectorStoreIndex.from_vector_store(self.summary_store)
            pair = (v_idx, s_idx)
            self._load_index_cache[doc_name] = pair
            index[doc_name] = pair
        self.logger("Index loaded successfully.")
        return index

    # 11️⃣
    def get_file_names(self) -> Dict[str, str]:
        mapping: Dict[str, str] = {}
        try:
            client = getattr(self.vector_store, "client", None)
            client = client() if callable(client) else client
            if client and hasattr(client, "list_nodes"):
                for n in client.list_nodes():
                    fp = (n.metadata or {}).get("file_path")
                    fh = (n.metadata or {}).get("file_hash")
                    if fp:
                        if fp not in mapping or (fh and not mapping.get(fp)):
                            mapping[fp] = fh
        except Exception:
            pass
        return mapping

    # 12️⃣
    def get_document_summary(self, doc_name: str) -> Optional[str]:
        try:
            s_idx = VectorStoreIndex.from_vector_store(self.summary_store)
            s_retr = VectorIndexRetriever(index=s_idx, similarity_top_k=5)
            hits = s_retr.retrieve(doc_name)
            for h in hits:
                return h.metadata.get("document_summary") or h.text
        except Exception:
            pass

