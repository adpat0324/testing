"""
file_tree.py

Hierarchical file tree builder and Streamlit selector for RAG knowledge base files.
Supports nested folders, per-folder “Select All”, global “Select All”,
and recursive search that expands only matching branches.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional, Set

import streamlit as st


class FileNode:
    """Represents a node in the file tree (folder or file)."""

    def __init__(self, name: str, is_file: bool = False, file_path: Optional[str] = None):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path  # Full path for file nodes
        self.children: Dict[str, "FileNode"] = {}

    def add_child(self, name: str, is_file: bool = False, file_path: Optional[str] = None) -> "FileNode":
        """Add a child node if not already present."""
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path)
        child = self.children[name]
        if is_file:
            child.is_file = True
            child.file_path = file_path
        return child

    def iter_children_sorted(self) -> Iterable["FileNode"]:
        for name in sorted(self.children):
            yield self.children[name]


class FileTreeBuilder:
    """Builds a hierarchical file tree from file metadata."""

    @staticmethod
    def build_tree(file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        """
        Build a tree from file metadata.

        Args:
            file_metadata: Mapping file_path -> metadata dict

        Returns:
            Dict mapping root category name -> FileNode
        """
        roots: Dict[str, FileNode] = {}

        for file_path, metadata in file_metadata.items():
            site_path = metadata.get("sitePath")
            site_name = metadata.get("siteName")
            drive_name = metadata.get("driveName")
            parent_path = metadata.get("parentPath")

            display_name = (
                metadata.get("name")
                or metadata.get("fileName")
                or metadata.get("file_name")
                or file_path.split("/")[-1]
            )

            if site_path and drive_name:
                # Build SharePoint hierarchy
                root_name = f"SharePoint: {site_name}" if site_name else site_path
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)

                current = roots[root_name]
                current = current.add_child(drive_name)

                if parent_path:
                    path_parts = [part for part in parent_path.strip("/").split("/") if part]
                    for part in path_parts:
                        current = current.add_child(part)

                current.add_child(display_name, is_file=True, file_path=file_path)

            else:
                # Other / flat structure
                root_name = "Other Files"
                if root_name not in roots:
                    roots[root_name] = FileNode(root_name)
                roots[root_name].add_child(display_name, is_file=True, file_path=file_path)

        return roots


class FileTreeSelector:
    """Interactive file tree selector with search and multi-level checkboxes."""

    def __init__(self, file_metadata: List[Dict]):
        self.file_metadata = self._iter_items(file_metadata)
        self.tree = FileTreeBuilder.build_tree(self.file_metadata)
        self.selected_files: Set[str] = set()
        self._checkbox_states: Dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _iter_items(file_metadata: List[Dict]) -> Dict[str, Dict]:
        """Convert list of metadata dicts to path->metadata mapping."""
        out: Dict[str, Dict] = {}
        for md in file_metadata:
            if not isinstance(md, dict):
                continue
            fp = md.get("file_path") or md.get("path")
            if fp:
                out[fp] = md
        return out

    def _file_checkbox_key(self, file_path: str) -> str:
        return f"file::{file_path}"

    def _folder_checkbox_key(self, parent_key: str, node_name: str) -> str:
        return f"folder::{parent_key}/{node_name}"

    def _get_all_files_in_node(self, node: FileNode) -> Set[str]:
        """Recursively collect all file paths under a node."""
        files: Set[str] = set()
        if node.is_file and node.file_path:
            files.add(node.file_path)
        for child in node.children.values():
            files.update(self._get_all_files_in_node(child))
        return files

    def _node_matches_search(self, node: FileNode, query: str) -> bool:
        """True if node or any descendant name contains query."""
        if not query:
            return True
        lowered = node.name.lower()
        if query in lowered:
            return True
        return any(self._node_matches_search(child, query) for child in node.children.values())

    def _set_files_under_node(self, node: FileNode, value: bool, parent_key: str = "") -> None:
        """Set all descendant nodes to the provided boolean value."""
        if node.is_file and node.file_path:
            key = self._file_checkbox_key(node.file_path)
            st.session_state[key] = value
            if value:
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
            return

        for child in node.children.values():
            child_parent_key = f"{parent_key}/{node.name}" if parent_key else node.name
            if not child.is_file:
                child_folder_key = self._folder_checkbox_key(child_parent_key, child.name)
                st.session_state[child_folder_key] = value
                self._checkbox_states[child_folder_key] = value
            self._set_files_under_node(child, value, child_parent_key)

    # ------------------------------------------------------------------
    # Recursive Renderer
    # ------------------------------------------------------------------
    def _render_node(
        self,
        node: FileNode,
        level: int = 0,
        parent_key: str = "",
        search_query: str = "",
        container=None,
    ) -> None:
        """Recursively render node (folder or file) with checkboxes."""
        if container is None:
            container = st

        if node.is_file and node.file_path:
            key = self._file_checkbox_key(node.file_path)
            checked = container.checkbox(
                node.name,
                value=st.session_state.get(key, node.file_path in self.selected_files),
                key=key,
            )

            if checked:
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
            return

        if not node.children:
            return

        expanded = level == 0 or bool(search_query)
        with container.expander(node.name, expanded=expanded):
            folder_key = self._folder_checkbox_key(parent_key, node.name)
            current_path = f"{parent_key}/{node.name}" if parent_key else node.name

            # Ensure folder checkbox state is initialised prior to widget
            # creation to avoid Streamlit's post-instantiation mutation error.
            if folder_key not in self._checkbox_states:
                inferred_state = st.session_state.get(folder_key, False)
                if parent_selected and not inferred_state:
                    inferred_state = True
                self._checkbox_states[folder_key] = inferred_state

            if folder_key not in st.session_state:
                st.session_state[folder_key] = self._checkbox_states[folder_key]

            folder_selected = container.checkbox("Select all", key=folder_key)

            previous_state = self._checkbox_states.get(folder_key, False)
            if folder_selected != previous_state:
                self._checkbox_states[folder_key] = folder_selected
                self._set_files_under_node(node, folder_selected, current_path)
            else:
                self._checkbox_states.setdefault(folder_key, folder_selected)

            for child in node.iter_children_sorted():
                if not self._node_matches_search(child, search_query):
                    continue
                self._render_node(
                    child,
                    level=level + 1,
                    parent_key=f"{parent_key}/{node.name}" if parent_key else node.name,
                    search_query=search_query,
                    container=container,
                )

    # ------------------------------------------------------------------
    # Main Renderer
    # ------------------------------------------------------------------
    def render(self, container=None) -> List[str]:
        """Render the entire tree and return selected file paths."""
        if container is None:
            container = st

        # Rebuild selected files from widget state so deselections propagate.
        self.selected_files = {
            key.split("::", 1)[1]
            for key, value in st.session_state.items()
            if key.startswith("file::") and value
        }

        # Search bar
        search_query = container.text_input("🔎 Search files", "").strip().lower()

        # Global select all toggle
        global_key = "global::select_all"
        previous_global = self._checkbox_states.get(global_key, False)
        global_selected = container.checkbox("Select all files", key=global_key, value=previous_global)
        if global_selected != previous_global:
            self._checkbox_states[global_key] = global_selected
            for root in self.tree.values():
                root_folder_key = self._folder_checkbox_key("root", root.name)
                st.session_state[root_folder_key] = global_selected
                self._checkbox_states[root_folder_key] = global_selected
                self._set_files_under_node(root, global_selected, "root")
        else:
            self._checkbox_states.setdefault(global_key, global_selected)

        # Sort so 'Other Files' is last
        root_names = sorted(self.tree.keys(), key=lambda x: (x == "Other Files", x.lower()))
        for root_name in root_names:
            root = self.tree[root_name]
            if not self._node_matches_search(root, search_query):
                continue
            self._render_node(
                root,
                level=0,
                parent_key="root",
                search_query=search_query,
                container=container,
            )

        container.caption(f"**{len(self.selected_files)}** files selected")
        return sorted(self.selected_files)
