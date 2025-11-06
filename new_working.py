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


def _build_tasks(self, documents: Dict[str, List[LlamaIndexDocument]], streamlit_off: bool = False):
    """
    Compare local document metadata with Risklab VectorStore hashes and prepare indexing tasks.
    Uses metadata-based file_hash and caches Risklab lookups to avoid repeated queries.
    """
    tasks = []
    self._cached_hashes = getattr(self, "_cached_hashes", {})  # persistent across updates

    try:
        for doc_name, docs in documents.items():
            try:
                # Get hash from document metadata (already computed in prepare_nodes)
                incoming_hash = docs[0].metadata.get("file_hash")
                if not incoming_hash:
                    self.logger.warning(f"⚠️ No file_hash in metadata for {doc_name}, skipping.")
                    continue

                # Retrieve existing hash, with in-memory caching to avoid repeated retriever calls
                existing_hash = self._cached_hashes.get(doc_name)
                if existing_hash is None:
                    existing_hash = self._get_file_hash_from_store(doc_name)
                    self._cached_hashes[doc_name] = existing_hash  # even if None, cache it

                # Compare hashes to decide what to do
                if not existing_hash:
                    self.logger.info(f"🆕 {doc_name}: New file detected — indexing.", streamlit_off=streamlit_off)
                    tasks.append((doc_name, docs, "new", streamlit_off))
                elif existing_hash != incoming_hash:
                    self.logger.info(f"🔄 {doc_name}: File changed — overwriting.", streamlit_off=streamlit_off)
                    tasks.append((doc_name, docs, "overwrite", streamlit_off))
                else:
                    self.logger.info(f"⏩ {doc_name}: Unchanged, skipping.", streamlit_off=streamlit_off)

            except Exception as e:
                self.logger.warning(f"⚠️ Error processing {doc_name}: {e}")
                tasks.append((doc_name, None, str(e)))

        self.logger.info(f"🧾 Prepared {len(tasks)} document(s) for indexing.")
        return tasks

    except Exception as e:
        self.logger.error(f"💥 Failed to build tasks for update_index: {e}")
        return []



def get_file_names(self) -> Dict[str, str]:
    """Fetch unique file names currently stored in the Risklab VectorStore using retrievers."""
    try:
        self.logger.info("🔍 Fetching indexed file names from Risklab VectorStore...")

        # Build retriever from the current Risklab VectorStore
        vector_index = VectorStoreIndex.from_vector_store(self.vector_store)
        retriever = VectorIndexRetriever(index=vector_index, similarity_top_k=1000)

        # Perform a broad retrieval to list all stored documents
        results = retriever.retrieve("")

        if not results:
            self.logger.info("📂 No indexed files found in Risklab VectorStore.")
            return {}

        file_names = {}
        for node in results:
            meta = getattr(node, "metadata", {}) or {}
            fname = meta.get("file_name")
            fpath = meta.get("file_path")
            if fname and fpath:
                file_names[fpath] = fname

        self.logger.info(f"📚 Retrieved {len(file_names)} indexed files from Risklab store.")
        return dict(sorted(file_names.items()))

    except Exception as e:
        self.logger.error(f"⚠️ Failed to fetch file names from Risklab store: {e}")
        return {}
