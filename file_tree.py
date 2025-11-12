# file_tree.py
from __future__ import annotations
from typing import Dict, List, Set, Optional
import re
import streamlit as st

# -----------------------------
# Tree data structures
# -----------------------------
class FileNode:
    """Represents a node in the file tree (folder or file)."""
    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path  # Full file_path for selection
        self.children: Dict[str, "FileNode"] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> "FileNode":
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        return self.children[name]


class FileTreeBuilder:
    """
    Build a hierarchical tree structure from file metadata.

    file_metadata: Dict[file_path, metadata dict]
      Expected keys if available: 'sitePath', 'siteName', 'driveName', 'parentPath'
    """
    @staticmethod
    def build_tree(file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        roots: Dict[str, FileNode] = {}

        for file_path, metadata in file_metadata.items():
            site_path = metadata.get("sitePath")
            site_name = metadata.get("siteName")
            drive_name = metadata.get("driveName")
            parent_path = metadata.get("parentPath")

            # SharePoint hierarchy
            if site_path and drive_name:
                root_name = f"SharePoint: {site_name if site_name else site_path}"
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)

                current = roots[root_name]
                current = current.add_child(f"📁 {drive_name}")

                # Parent folders (split on '/')
                if parent_path:
                    for part in filter(None, parent_path.strip("/").split("/")):
                        current = current.add_child(f"📂 {part}")

                # The file
                current.add_child(f"📄 {file_path}", is_file=True, file_path=file_path)

            else:
                # Flat "Other Files"
                root_name = "Other Files"
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)
                roots[root_name].add_child(f"📄 {file_path}", is_file=True, file_path=file_path)

        return roots

# -----------------------------
# Selector component
# -----------------------------
class FileTreeSelector:
    """
    Interactive file tree selector with search and a working Select All that applies
    to the *visible* files (after filtering).

    Usage:
        file_metadata = index_manager.get_file_metadata()
        selector = FileTreeSelector(file_metadata, state_key="fts")
        selected_paths = selector.render(container=st.sidebar)
    """

    def __init__(self, file_metadata: Dict[str, Dict], *, state_key: str = "fts"):
        self.file_metadata = file_metadata or {}
        self.tree = FileTreeBuilder.build_tree(self.file_metadata)
        self.state_key = state_key

        # Session keys (none of these are widget keys, so we can freely write to them)
        self._sel_set_key = f"{self.state_key}_selected_set"     # Set[str]
        self._search_key  = f"{self.state_key}_search"            # str
        self._sel_all_key = f"{self.state_key}_select_all"        # widget key (read-only by us)
        self._sel_all_trg = f"{self.state_key}_select_all_trig"   # bool trigger set by on_change
        self._last_query  = f"{self.state_key}_last_query"        # last applied query

        if self._sel_set_key not in st.session_state:
            st.session_state[self._sel_set_key] = set()  # type: ignore[assignment]
        if self._search_key not in st.session_state:
            st.session_state[self._search_key] = ""
        if self._sel_all_trg not in st.session_state:
            st.session_state[self._sel_all_trg] = False
        if self._last_query not in st.session_state:
            st.session_state[self._last_query] = ""

    # ---------- filtering ----------
    @staticmethod
    def _matches(text: str, query: str) -> bool:
        if not query:
            return True
        return query.lower() in text.lower()

    def _file_label(self, node: FileNode) -> str:
        # Prefer display name from metadata if present, else node.name (already prefixed with icons)
        if node.file_path and node.file_path in self.file_metadata:
            meta = self.file_metadata[node.file_path]
            return meta.get("file_name") or node.name
        return node.name

    def _filter_tree(self, node: FileNode, query: str) -> Optional[FileNode]:
        """
        Keep node if:
          - it's a FILE and file label/path matches query
          - it's a FOLDER with ANY matching descendant
        If a folder name matches the query, we *still only include matching descendants*
        (to avoid dumping the entire folder as you requested).
        """
        if node.is_file:
            label = self._file_label(node)
            if self._matches(label, query) or self._matches(node.file_path or "", query):
                return FileNode(label, True, node.file_path)
            return None

        # Folder: check children recursively
        filtered_children: Dict[str, FileNode] = {}
        for child in node.children.values():
            filtered = self._filter_tree(child, query)
            if filtered:
                filtered_children[filtered.name] = filtered

        if filtered_children:
            new_node = FileNode(node.name, False, None)
            new_node.children = filtered_children
            return new_node

        return None

    def _collect_visible_files(self, node: FileNode) -> List[str]:
        """Collect file_paths of *visible* files under filtered node."""
        stack = [node]
        out: List[str] = []
        while stack:
            cur = stack.pop()
            if cur.is_file and cur.file_path:
                out.append(cur.file_path)
            stack.extend(cur.children.values())
        return out

    # ---------- select-all callback ----------
    def _on_select_all_changed(self):
        # We don't mutate the checkbox state itself; just trigger handling in render()
        st.session_state[self._sel_all_trg] = True

    # ---------- rendering ----------
    def _render_node(self, node: FileNode, level: int = 0):
        """Render a node (checkbox for files, expander for folders)."""
        if node.is_file and node.file_path:
            key = f"{self.state_key}_cb::{node.file_path}"
            checked = node.file_path in st.session_state[self._sel_set_key]
            if st.checkbox(self._file_label(node), value=checked, key=key):
                st.session_state[self._sel_set_key].add(node.file_path)
            else:
                st.session_state[self._sel_set_key].discard(node.file_path)
            return

        # Folder
        with st.expander(node.name, expanded=(level < 1)):
            for child in sorted(node.children.values(), key=lambda n: n.name.lower()):
                self._render_node(child, level + 1)

    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None) -> List[str]:
        """Render the complete file tree and return selected file paths."""
        if container is None:
            container = st

        with container:
            # Search (kept simple & fast)
            query = st.text_input("🔎 Search files", value=st.session_state[self._search_key], key=self._search_key).strip()
            filtered_roots: Dict[str, FileNode] = {}
            for root_name in sorted(self.tree.keys()):
                filtered = self._filter_tree(self.tree[root_name], query)
                if filtered:
                    filtered_roots[root_name] = filtered

            # CSS cap for the scroll area
            st.markdown(
                """
                <style>
                  .fts-scroll { max-height: 380px; overflow-y: auto; padding-right: .25rem; }
                </style>
                """,
                unsafe_allow_html=True,
            )

            # Select All (works on *visible* files only)
            st.checkbox(
                "Select All (visible)",
                key=self._sel_all_key,
                on_change=self._on_select_all_changed,
                help="Toggle to select/unselect all files currently visible (after search).",
            )

            # If toggled, update the selection set based on visible files
            if st.session_state[self._sel_all_trg]:
                visible: List[str] = []
                for root in filtered_roots.values():
                    visible.extend(self._collect_visible_files(root))

                if st.session_state[self._sel_all_key]:
                    # Select all visible
                    st.session_state[self._sel_set_key] = set(visible)
                else:
                    # Unselect all visible (leave others as-is)
                    st.session_state[self._sel_set_key] -= set(visible)

                # reset trigger
                st.session_state[self._sel_all_trg] = False

            # Render the filtered tree inside a scrollable area
            scroll = st.container()
            with scroll:
                st.markdown('<div class="fts-scroll">', unsafe_allow_html=True)
                for root_name in sorted(filtered_roots.keys()):
                    self._render_node(filtered_roots[root_name], level=0)
                st.markdown("</div>", unsafe_allow_html=True)

            # Footer count
            selected = sorted(st.session_state[self._sel_set_key])
            st.caption(f"**{len(selected)}** files selected")

            return selected



