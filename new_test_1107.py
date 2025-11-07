import os
import hashlib
from typing import Dict, List

from llama_index.core import Document as LlamaIndexDocument
from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever
from llama_index.core.node_parser import SentenceSplitter
from llama_index.readers.file import PDFReader

from risklab_vector_store import RisklabVectorStore  # your import
from settings import Settings


class IndexManager:
    """
    Handles:
      • Preparing nodes from SharePoint files
      • Detecting new/updated documents via hash
      • Updating Risklab vector & summary stores
      • Listing indexed files for the chatbot UI
    """

    def __init__(self, logger):
        self.logger = logger
        self.vector_store = RisklabVectorStore("kb_vector_store")
        self.summary_store = RisklabVectorStore("kb_summary_store")
        self._cached_hashes = {}

    # -----------------------------------------------------
    # HASH HELPER
    # -----------------------------------------------------
    def _compute_file_hash(self, text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()

    # -----------------------------------------------------
    # PREPARE LLAMAINDEX DOCS
    # -----------------------------------------------------
    def prepare_documents(self, sharepoint_files: Dict[str, dict]):
        """
        sharepoint_files = {
            file_path: {
                "text": "...",
                "file_name": "...",
                "file_id": "...",
                "raw_bytes": b"..."
            }
        }
        """
        documents = {}

        for file_path, info in sharepoint_files.items():
            file_name = info["file_name"]
            text = info["text"]

            file_hash = self._compute_file_hash(text)

            doc = LlamaIndexDocument(
                text=text,
                metadata={
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_hash": file_hash,
                    "file_id": info.get("file_id"),
                    "node_type": "TextNode",
                    "source": "sharepoint"
                }
            )

            documents[file_path] = [doc]

        return documents

    # -----------------------------------------------------
    # GET STORED HASH FROM VECTOR STORE
    # -----------------------------------------------------
    def _get_file_hash_from_store(self, file_name: str):
        try:
            index = VectorStoreIndex.from_vector_store(self.vector_store)
            retriever = VectorIndexRetriever(index=index, similarity_top_k=1000)

            # TextNode → full doc nodes
            results = retriever.retrieve("TextNode")

            for node in results:
                if node.metadata.get("file_name") == file_name:
                    return node.metadata.get("file_hash")

            return None
        except Exception as e:
            self.logger.error(f"Error getting stored hash for {file_name}: {e}")
            return None

    # -----------------------------------------------------
    # BUILD TASKS (new vs overwrite)
    # -----------------------------------------------------
    def _build_tasks(self, documents):
        tasks = []

        for file_path, doc_list in documents.items():
            file_name = doc_list[0].metadata["file_name"]
            incoming_hash = doc_list[0].metadata["file_hash"]

            cached = self._cached_hashes.get(file_name)
            if cached is None:
                cached = self._get_file_hash_from_store(file_name)
                self._cached_hashes[file_name] = cached

            if not cached:
                tasks.append((file_path, doc_list, "new"))
            elif cached != incoming_hash:
                tasks.append((file_path, doc_list, "overwrite"))
            else:
                self.logger.info(f"Skipping unchanged file: {file_name}")

        return tasks

    # -----------------------------------------------------
    # DELETE OLD EMBEDDINGS FOR FILE
    # -----------------------------------------------------
    def _delete_document(self, file_name: str):
        # Vector deletion
        try:
            vindex = VectorStoreIndex.from_vector_store(self.vector_store)
            vretriever = VectorIndexRetriever(index=vindex, similarity_top_k=1000)
            for node in vretriever.retrieve("TextNode"):
                if node.metadata.get("file_name") == file_name:
                    self.vector_store.delete(node.node_id)
            self.logger.info(f"✅ Deleted vector embeddings for {file_name}")
        except Exception as e:
            self.logger.error(f"Failed vector deletion for {file_name}: {e}")

        # Summary deletion
        try:
            sindex = VectorStoreIndex.from_vector_store(self.summary_store)
            sretriever = VectorIndexRetriever(index=sindex, similarity_top_k=1000)
            for node in sretriever.retrieve("Document"):
                if node.metadata.get("file_name") == file_name:
                    self.summary_store.delete(node.node_id)
            self.logger.info(f"✅ Deleted summary embeddings for {file_name}")
        except Exception as e:
            self.logger.error(f"Failed summary deletion for {file_name}: {e}")

    # -----------------------------------------------------
    # SAVE NEW EMBEDDINGS
    # -----------------------------------------------------
    def _save_document(self, file_path: str, docs, file_name: str):
        splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)

        # Vector nodes
        nodes = splitter.get_nodes_from_documents(docs)
        for node in nodes:
            node.metadata["file_name"] = file_name
            node.metadata["file_path"] = file_path

        self.vector_store.add(Settings.embed_model(nodes))
        self.logger.info(f"🧠 Added {len(nodes)} vector nodes: {file_name}")

        # Summary nodes
        summary_nodes = []
        for doc in docs:
            summary_prompt = (
                f"Summarize in 5 concise sentences:\n\n{doc.text}"
            )
            summary_text = Settings.llm.complete(summary_prompt)
            sdoc = LlamaIndexDocument(
                text=str(summary_text),
                metadata=doc.metadata
            )
            summary_nodes.extend(splitter.get_nodes_from_documents([sdoc]))

        self.summary_store.add(Settings.embed_model(summary_nodes))
        self.logger.info(f"🧾 Added {len(summary_nodes)} summary nodes: {file_name}")

    # -----------------------------------------------------
    # UPDATE INDEX (ENTRYPOINT FOR SCHEDULED JOB)
    # -----------------------------------------------------
    def update_index(self, sharepoint_files):
        documents = self.prepare_documents(sharepoint_files)
        tasks = self._build_tasks(documents)

        for file_path, docs, action in tasks:
            file_name = docs[0].metadata["file_name"]
            if action == "overwrite":
                self._delete_document(file_name)
            if action in ("new", "overwrite"):
                self._save_document(file_path, docs, file_name)

        self.logger.info(f"✅ Indexed {len(tasks)} documents.")

    # -----------------------------------------------------
    # LIST FILES FOR CHATBOT UI
    # -----------------------------------------------------
    def get_file_names(self):
        """
        Returns {file_path: file_name} for UI dropdown.
        """
        file_map = {}
        try:
            vindex = VectorStoreIndex.from_vector_store(self.vector_store)
            retriever = VectorIndexRetriever(index=vindex, similarity_top_k=1000)
            for node in retriever.retrieve("TextNode"):
                fname = node.metadata.get("file_name")
                fpath = node.metadata.get("file_path")
                if fname and fpath:
                    file_map[fpath] = fname
        except Exception as e:
            self.logger.error(f"Failed to fetch file names: {e}")

        return dict(sorted(file_map.items()))
