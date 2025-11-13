from typing import Dict, List, Optional, Set, Tuple
import streamlit as st


class FileNode:
    """Represents a node in the file tree (folder or file)."""

    def __init__(
        self,
        name: str,
        is_file: bool = False,
        file_path: Optional[str] = None,
        path: Optional[Tuple[str, ...]] = None,
    ):
        self.name = name
        self.is_file = is_file
        self.file_path = file_path
        # Tuple representing the node's location from the tree root
        self.path: Tuple[str, ...] = path or (name,)
        self.children: Dict[str, "FileNode"] = {}

    def add_child(
        self, name: str, is_file: bool = False, file_path: Optional[str] = None
    ) -> "FileNode":
        """Add or get a child node."""
        child_path = (*self.path, name)
        if name not in self.children:
            self.children[name] = FileNode(name, is_file, file_path, child_path)
        else:
            child = self.children[name]
            # Ensure existing nodes keep the most up to date metadata
            if is_file:
                child.is_file = True
                child.file_path = file_path
            child.path = child_path
        return self.children[name]


class FileTreeSelector:
    """Interactive hierarchical file tree selector with search, scroll, and working select-all."""

    def __init__(self, file_metadata: Dict[str, Dict]):
        self.file_metadata = file_metadata or {}
        self.tree: Dict[str, FileNode] = self._build_tree(file_metadata)
        self.selected_files: Set[str] = set()

    # --------------------------------------------------------------------------
    # Build a hierarchical tree from file metadata
    def _build_tree(self, file_metadata: Dict[str, Dict]) -> Dict[str, FileNode]:
        roots: Dict[str, FileNode] = {}

        for file_path, metadata in file_metadata.items():
            # Split by slashes to form hierarchy
            parts = [p for p in file_path.strip("/").split("/") if p]
            if not parts:
                continue

            root_name = parts[0]
            if root_name not in roots:
                roots[root_name] = FileNode(root_name, path=(root_name,))

            current = roots[root_name]
            for part in parts[1:-1]:
                current = current.add_child(part)
            current.add_child(parts[-1], is_file=True, file_path=file_path)

        return roots

    # --------------------------------------------------------------------------
    # Recursive search helpers
    def _collect_matches(
        self, node: FileNode, query: str, matches: Set[Tuple[str, ...]]
    ) -> bool:
        """Collect node paths that should remain visible during a search."""

        if not query:
            return True

        clean_query = query.lower()
        match_self = clean_query in node.name.lower()

        descendant_match = False
        for child in node.children.values():
            if self._collect_matches(child, query, matches):
                descendant_match = True

        if match_self or descendant_match:
            matches.add(node.path)
            return True

        return False

    def _get_all_files(self, node: FileNode) -> Set[str]:
        """Recursively collect all file paths under a node."""
        files = set()
        if node.is_file and node.file_path:
            files.add(node.file_path)
        for child in node.children.values():
            files.update(self._get_all_files(child))
        return files

    # --------------------------------------------------------------------------
    # Recursive renderer
    def _render_node(
        self,
        node: FileNode,
        level: int = 0,
        parent_selected: bool = False,
        search_active: bool = False,
        matches: Optional[Set[Tuple[str, ...]]] = None,
    ):
        """Render each folder/file recursively with checkboxes."""
        indent = " " * level  # Unicode em space for hierarchy indentation

        node_key = "/".join(node.path)

        if search_active and matches is not None and node.path not in matches:
            return

        if node.is_file:
            checked = node.file_path in self.selected_files or parent_selected
            if st.checkbox(
                f"{indent}📄 {node.name}", value=checked, key=node.file_path
            ):
                self.selected_files.add(node.file_path)
            else:
                self.selected_files.discard(node.file_path)
        else:
            # Folder expander with “Select all in folder”
            expanded = parent_selected or (
                search_active and matches is not None and node.path in matches
            )
            with st.expander(f"{indent}📁 {node.name}", expanded=expanded):
                folder_files = self._get_all_files(node)
                folder_selected = all(f in self.selected_files for f in folder_files)

                select_all_key = f"fts_select::{node_key}"
                prev_state = st.session_state.get(select_all_key, folder_selected)
                checkbox_value = st.checkbox(
                    f"Select all in '{node.name}'",
                    value=folder_selected,
                    key=select_all_key,
                )

                if checkbox_value != prev_state:
                    # User toggled the checkbox during this run
                    if checkbox_value:
                        self.selected_files.update(folder_files)
                    else:
                        self.selected_files.difference_update(folder_files)
                    folder_selected = checkbox_value
                else:
                    # Keep UI in sync with the actual selection state
                    if folder_selected != checkbox_value:
                        st.session_state[select_all_key] = folder_selected
                        checkbox_value = folder_selected

                children = sorted(node.children.values(), key=lambda n: n.name.lower())
                if search_active and matches is not None:
                    children = [child for child in children if child.path in matches]

                for child in children:
                    self._render_node(
                        child,
                        level + 1,
                        parent_selected=folder_selected,
                        search_active=search_active,
                        matches=matches,
                    )

    # --------------------------------------------------------------------------
    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None) -> List[str]:
        """Main renderer entry point."""
        if container is None:
            container = st

        # Search input
        search_query = container.text_input("🔍 Search files and folders", "").strip()

        # Scrollable container
        with container.container():
            container.markdown(
                """
                <style>
                div[data-testid="stVerticalBlock"] div[data-testid="stVerticalBlock"] {
                    max-height: 450px;
                    overflow-y: auto;
                    padding-right: 0.5rem;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            # Global select all
            all_files = set()
            for root in self.tree.values():
                all_files.update(self._get_all_files(root))
            all_selected = len(all_files) > 0 and self.selected_files.issuperset(all_files)

            def toggle_all():
                if st.session_state["fts_select_all"]:
                    self.selected_files.update(all_files)
                else:
                    self.selected_files.clear()

            container.checkbox(
                "Select All Files",
                key="fts_select_all",
                value=all_selected,
                on_change=toggle_all,
            )

        # Determine nodes to keep visible when searching
        matches: Optional[Set[Tuple[str, ...]]] = None
        if search_query:
            matches = set()
            for root_node in self.tree.values():
                self._collect_matches(root_node, search_query, matches)

        # Render tree honoring search matches
        for root_name, root_node in sorted(self.tree.items()):
            self._render_node(
                root_node,
                level=0,
                parent_selected=False,
                search_active=bool(search_query),
                matches=matches,
            )

            container.caption(f"**{len(self.selected_files)}** files selected")

        return list(self.selected_files)
