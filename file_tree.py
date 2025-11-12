from typing import Dict, List, Optional
import streamlit as st


class FileTreeSelector:
    """
    Flat, searchable, scrollable file selector with a working Select All checkbox.
    Compatible with previous API:
      selected = FileTreeSelector(file_metadata).render(container)
    """

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata or {}

        # Build file list and labels
        self.file_paths: List[str] = sorted(self.file_metadata.keys())
        self.labels = {
            p: self.file_metadata.get(p, {}).get("file_name") or p for p in self.file_paths
        }

        # Streamlit state keys
        self.key_prefix = "fts"
        self.selected_key = f"{self.key_prefix}_selected"
        self.select_all_key = f"{self.key_prefix}_select_all"

        # Initialize state
        if self.selected_key not in st.session_state:
            st.session_state[self.selected_key] = []
        if self.select_all_key not in st.session_state:
            st.session_state[self.select_all_key] = False

    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None) -> List[str]:
        """
        Render searchable, scrollable file selector with Select All.
        """
        if container is None:
            container = st

        # --- Search bar ---
        search_query = container.text_input("🔍 Search files", "").strip().lower()

        # Filter matching files (recursively match full path and metadata)
        if search_query:
            filtered_files = [
                p for p in self.file_paths
                if search_query in p.lower() or search_query in self.labels[p].lower()
            ]
        else:
            filtered_files = self.file_paths

        # --- Select All ---
        # Compute whether all visible files are selected
        all_visible_selected = (
            len(filtered_files) > 0
            and all(p in st.session_state[self.selected_key] for p in filtered_files)
        )

        # Avoid modifying widget state directly; use callbacks instead
        def toggle_select_all():
            if st.session_state[self.select_all_key]:
                st.session_state[self.selected_key] = list(filtered_files)
            else:
                st.session_state[self.selected_key] = [
                    p for p in st.session_state[self.selected_key] if p not in filtered_files
                ]

        container.checkbox(
            "Select All",
            value=all_visible_selected,
            key=self.select_all_key,
            on_change=toggle_select_all,
        )

        # --- Scrollable multi-select ---
        # Streamlit multiselect is searchable & scrollable, but we apply height styling
        container.markdown(
            """
            <style>
            div[data-baseweb="select"] > div {
                max-height: 400px;
                overflow-y: auto;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )

        selected = container.multiselect(
            "📂 Files",
            options=filtered_files,
            default=[p for p in st.session_state[self.selected_key] if p in filtered_files],
            format_func=lambda p: self.labels.get(p, p),
            key=f"{self.key_prefix}_multiselect",
            placeholder="Search or scroll files...",
        )

        # Sync selection
        st.session_state[self.selected_key] = selected

        # --- Count footer ---
        container.caption(f"**{len(selected)}** file(s) selected")

        return selected




