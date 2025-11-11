# file_tree.py
from typing import Dict, List, Set, Optional
import streamlit as st

from typing import Dict, List, Set, Optional
import streamlit as st

# ============================================================
#  Original Classes (kept for compatibility)
# ============================================================

class FileNode:
    """Represents a node in the file tree (folder or file)."""
    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path
        self.children: Dict[str, 'FileNode'] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> 'FileNode':
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        return self.children[name]


class FileTreeBuilder:
    """Build a hierarchical tree structure from file metadata."""

    @staticmethod
    def build_tree(file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        roots = {}

        for file_path, metadata in file_metadata.items():
            site_name = metadata.get("sitePath")
            drive_name = metadata.get("driveName")
            parent_path = metadata.get("parentPath")

            # Determine the root name
            if site_name and drive_name:
                root_name = f"{site_name}/{drive_name}"
            elif site_name:
                root_name = site_name
            else:
                root_name = "Other Files"

            # Create root node if needed
            if root_name not in roots:
                roots[root_name] = FileNode(root_name)

            current = roots[root_name]

            # Build folder structure
            if parent_path:
                for part in parent_path.strip("/").split("/"):
                    current = current.add_child(part)

            # Add file
            current.add_child(file_path, is_file=True, file_path=file_path)

        return roots


# ============================================================
#  New Flat File Selector (Searchable, Scrollable)
# ============================================================

class FileTreeSelector:
    """
    Flat searchable file selector with Select All.
    Does not use the tree for UI, but original classes remain for compatibility.
    """

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata or {}

        # Build flat option list (paths)
        self.options: List[str] = sorted(self.file_metadata.keys(), key=lambda x: x.lower())

        # Session keys (persistent but safe)
        self._search_key = "fts_search"
        self._all_key = "fts_select_all"
        self._ms_key = "fts_multiselect"

        if self._search_key not in st.session_state:
            st.session_state[self._search_key] = ""

        if self._all_key not in st.session_state:
            st.session_state[self._all_key] = False

        if self._ms_key not in st.session_state:
            st.session_state[self._ms_key] = []

    # ---------------------------------------------------------
    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None,
               height: int = 350) -> List[str]:

        if container is None:
            container = st

        # Search box
        search_val = container.text_input(
            "Search documents",
            key=self._search_key,
            placeholder="Search…"
        ).lower()

        filtered = [p for p in self.options if search_val in p.lower()]

        # Select All toggle
        def toggle_all():
            if st.session_state[self._all_key]:
                st.session_state[self._ms_key] = filtered.copy()
            else:
                st.session_state[self._ms_key] = []

        container.checkbox(
            "Select All",
            key=self._all_key,
            on_change=toggle_all,
        )

        # Scrollable multiselect using CSS
        container.markdown(
            f"""
            <style>
            .fts-scroll-box {{
                max-height: {height}px;
                overflow-y: auto;
                border: 1px solid #CCC;
                border-radius: 6px;
                padding: 6px;
            }}
            </style>
            """,
            unsafe_allow_html=True
        )

        container.markdown('<div class="fts-scroll-box">', unsafe_allow_html=True)

        selected = container.multiselect(
            "",
            options=filtered,
            default=st.session_state[self._ms_key],
            key=self._ms_key,
        )

        container.markdown("</div>", unsafe_allow_html=True)

        # Sync back
        st.session_state[self._ms_key] = selected
        st.session_state[self._all_key] = (
            len(filtered) > 0 and len(selected) == len(filtered)
        )

        # Footer
        container.caption(f"**{len(selected)} files selected**")

        return selected
