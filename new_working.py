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


def _build_tasks(self, documents: Dict[str, list], streamlit_off: bool = False):
    """
    Compare local documents with Risklab VectorStore and prepare a list of indexing tasks.

    Returns:
        list[tuple]: [(doc_name, nodes, err)] for processing by update_index().
    """
    tasks = []
    self._cached_hashes = {}  # simple session cache to reduce repeated retriever calls

    try:
        # Step 1: Get all stored file names from Risklab store
        stored_files = self.get_file_names()
        if not stored_files:
            self.logger.info("🆕 No files currently indexed — all local files will be added.")

        # Step 2: Iterate through local documents to compare hashes and prepare indexing tasks
        for doc_name, doc_nodes in documents.items():
            try:
                # Compute current file hash
                file_hash = self._compute_file_hash(doc_name)
                if not file_hash:
                    raise ValueError("File hash could not be computed.")

                # Check Risklab store for existing hash
                existing_hash = self._cached_hashes.get(doc_name)
                if not existing_hash:
                    existing_hash = self._get_file_hash_from_store(doc_name)
                    if existing_hash:
                        self._cached_hashes[doc_name] = existing_hash

                # Step 3: Determine if update is needed
                if existing_hash == file_hash:
                    self.logger.info(f"⏩ Skipping {doc_name} (hash unchanged).")
                    continue

                # Step 4: Prepare task for reindexing
                self.logger.info(f"📄 Queued {doc_name} for indexing (new or updated).")
                tasks.append((doc_name, doc_nodes, None))

            except Exception as e:
                self.logger.warning(f"⚠️ Skipping {doc_name} due to error: {e}")
                tasks.append((doc_name, None, str(e)))

    except Exception as e:
        self.logger.error(f"💥 Failed to build tasks for update_index: {e}")
        tasks.append(("__global__", None, str(e)))

    # Step 5: Log summary
    self.logger.info(f"🧾 Prepared {len(tasks)} documents for indexing.")
    return tasks


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
