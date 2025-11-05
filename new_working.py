from llama_index.core import VectorStoreIndex
from llama_index.core.retrievers import VectorIndexRetriever

def _get_file_hash_from_store(self, doc_name: str) -> Optional[str]:
    """Retrieve the stored file hash for a document by its file_path using a retriever."""
    try:
        # Build retriever from the existing vector store
        vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
        retriever = VectorIndexRetriever(index=vector_index, similarity_top_k=5)

        # Retrieve a small set of nodes that might match the document name
        results = retriever.retrieve(doc_name)

        for node in results:
            meta = getattr(node, "metadata", {}) or {}
            if meta.get("file_path") == doc_name:
                file_hash = meta.get("file_hash")
                if file_hash:
                    self.logger.debug(f"Found stored file hash for {doc_name}: {file_hash}")
                    return file_hash

        self.logger.debug(f"No stored file hash found for {doc_name}.")
        return None

    except Exception as e:
        self.logger.warning(f"⚠️ Could not retrieve file hash for {doc_name}: {e}")
        return None


def _build_tasks(self, documents, streamlit_off=False):
    self._cached_hashes = {}
    ...
    for doc_name, doc_nodes in documents.items():
        existing_hash = self._cached_hashes.get(doc_name)
        if not existing_hash:
            existing_hash = self._get_file_hash_from_store(doc_name)
            if existing_hash:
                self._cached_hashes[doc_name] = existing_hash

def get_all_file_names(self) -> Dict[str, str]:
    all_files = {}
    for store in [self.vector_store, self.summary_store]:
        index = VectorStoreIndex.from_vector_store(store)
        retriever = VectorIndexRetriever(index=index, similarity_top_k=1000)
        for node in retriever.retrieve(""):
            meta = getattr(node, "metadata", {}) or {}
            fname = meta.get("file_name")
            fpath = meta.get("file_path")
            if fname and fpath:
                all_files[fpath] = fname
    return dict(sorted(all_files.items()))
