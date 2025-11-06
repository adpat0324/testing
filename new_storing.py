def _delete_document(self, file_name: str):
    """Delete all vector + summary nodes for a given file_name."""
    # Delete from vector_store
    try:
        vindex = VectorStoreIndex.from_vector_store(self.vector_store)
        vretriever = VectorIndexRetriever(index=vindex, similarity_top_k=1000)
        vector_results = vretriever.retrieve("TextNode")

        for node in vector_results:
            if node.metadata.get("file_name") == file_name:
                self.vector_store.delete(node.node_id)

        self.logger.info(f"✅ Deleted old vector embeddings for {file_name}")
    except Exception as e:
        self.logger.error(f"❌ Failed deleting vector embeddings for {file_name}: {e}")

    # Delete from summary_store
    try:
        sindex = VectorStoreIndex.from_vector_store(self.summary_store)
        sretriever = VectorIndexRetriever(index=sindex, similarity_top_k=1000)
        summary_results = sretriever.retrieve("Document")

        for node in summary_results:
            if node.metadata.get("file_name") == file_name:
                self.summary_store.delete(node.node_id)

        self.logger.info(f"✅ Deleted old summary embeddings for {file_name}")
    except Exception as e:
        self.logger.error(f"❌ Failed deleting summary embeddings for {file_name}: {e}")

def _save_document_embeddings(self, file_path: str, docs, file_name: str):
    """Embed nodes + summaries and save to vector + summary stores."""

    splitter = SentenceSplitter(chunk_size=512, chunk_overlap=50)

    # ✅ Split into nodes
    nodes = splitter.get_nodes_from_documents(docs)
    for node in nodes:
        node.metadata["file_name"] = file_name
        node.metadata["file_path"] = file_path

    # ✅ Add vector embeddings
    self.vector_store.add(Settings.embed_model(nodes))
    self.logger.info(f"🧠 Added {len(nodes)} vector nodes for {file_name}")

    # ✅ Build summaries
    def summarize_document(doc: Document):
        summary_prompt = f"Summarize in 5 concise sentences:\n\n{doc.text}"
        summary_text = Settings.llm.complete(summary_prompt)
        return Document(text=str(summary_text),
                        metadata={"file_name": file_name, "file_path": file_path})

    summary_docs = [summarize_document(d) for d in docs]
    summary_nodes = splitter.get_nodes_from_documents(summary_docs)

    for snode in summary_nodes:
        snode.metadata["file_name"] = file_name
        snode.metadata["file_path"] = file_path

    # ✅ Add summary embeddings
    self.summary_store.add(Settings.embed_model(summary_nodes))
    self.logger.info(f"🧾 Added {len(summary_nodes)} summary nodes for {file_name}")


def _build_tasks(self, documents):
    tasks = []
    self._cached_hashes = {}

    existing_files = self.get_file_names()  # vector_store only

    for file_path, docs in documents.items():
        file_name = docs[0].metadata.get("file_name")
        incoming_hash = docs[0].metadata.get("file_hash")

        # Get stored hash (cached or from store)
        existing_hash = self._cached_hashes.get(file_name)
        if existing_hash is None:
            existing_hash = self._get_file_hash_from_store(file_name)
            self._cached_hashes[file_name] = existing_hash

        if not existing_hash:
            tasks.append((file_path, docs, "new"))
        elif existing_hash != incoming_hash:
            tasks.append((file_path, docs, "overwrite"))
        else:
            self.logger.info(f"Skipping unchanged {file_name}")

    return tasks


def update_index(self, tasks):
    for file_path, docs, action in tasks:
        file_name = docs[0].metadata.get("file_name")

        if action == "overwrite":
            self.logger.info(f"♻️ Updating existing file {file_name}")
            self._delete_document(file_name)

        if action in ("new", "overwrite"):
            self.logger.info(f"📥 Indexing file {file_name}")
            self._save_document_embeddings(file_path, docs, file_name)

    self.logger.info(f"✅ Indexed {len(tasks)} documents successfully.")
