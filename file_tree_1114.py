class FileTreeSelector:
    """Interactive file tree selector with search and multi-level checkboxes."""
    
    def __init__(self, file_metadata: List[Dict]):
        self.file_metadata = self._iter_items(file_metadata)
        self.tree = FileTreeBuilder.build_tree(self.file_metadata)
        self.selected_files: Set[str] = set()
        self._checkbox_states: Dict[str, bool] = {}
    
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
        return f"folder::{parent_key}/{node_name}" if parent_key else f"folder::{node_name}"
    
    def _get_all_files_in_node(self, node: FileNode, search_query: str = "") -> Set[str]:
        """Recursively collect all file paths under a node that match search."""
        files: Set[str] = set()
        if node.is_file and node.file_path:
            if self._node_matches_search(node, search_query):
                files.add(node.file_path)
        for child in node.children.values():
            files.update(self._get_all_files_in_node(child, search_query))
        return files
    
    def _node_matches_search(self, node: FileNode, query: str) -> bool:
        """True if node or any descendant name contains query."""
        if not query:
            return True
        lowered = node.name.lower()
        if query in lowered:
            return True
        return any(self._node_matches_search(child, query) for child in node.children.values())
    
    def _set_files_under_node(self, node: FileNode, value: bool, parent_key: str = "", search_query: str = "") -> None:
        """Set all descendant nodes to the provided boolean value, respecting search filter."""
        if node.is_file and node.file_path:
            # Only modify if it matches the search query
            if self._node_matches_search(node, search_query):
                key = self._file_checkbox_key(node.file_path)
                st.session_state[key] = value
                if value:
                    self.selected_files.add(node.file_path)
                else:
                    self.selected_files.discard(node.file_path)
            return  # Important: return here for file nodes
        
        # For folder nodes, recursively process all children
        for child in node.children.values():
            child_parent_key = f"{parent_key}/{node.name}" if parent_key else node.name
            
            if not child.is_file:
                # Update the child folder's "Select all" checkbox state
                if self._node_matches_search(child, search_query):
                    child_folder_key = self._folder_checkbox_key(child_parent_key, child.name)
                    st.session_state[child_folder_key] = value
                    self._checkbox_states[child_folder_key] = value
            
            # Recursively process this child (whether it's a file or folder)
            self._set_files_under_node(child, value, child_parent_key, search_query)
    
    def _folder_checkbox_callback(self, node: FileNode, folder_key: str, current_path: str, search_query: str):
        """Callback for folder 'Select all' checkbox changes."""
        folder_selected = st.session_state[folder_key]
        previous_state = self._checkbox_states.get(folder_key, False)
        
        # Only act if state actually changed
        if folder_selected != previous_state:
            self._checkbox_states[folder_key] = folder_selected
            # Apply change to all descendants that match search
            self._set_files_under_node(node, folder_selected, current_path, search_query)
    
    def _render_node(self, node: FileNode, level: int = 0, parent_key: str = "", parent_selected: bool = False, search_query: str = "", container=None) -> None:
        """Recursively render node (folder or file) with checkboxes."""
        if container is None:
            container = st
        
        if node.is_file and node.file_path:
            key = self._file_checkbox_key(node.file_path)
            if parent_selected:
                st.session_state[key] = True
                self.selected_files.add(node.file_path)
            
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
            
            # Ensure folder checkbox state is initialized prior to widget
            # creation to avoid Streamlit's post-instantiation mutation error.
            if folder_key not in self._checkbox_states:
                self._checkbox_states[folder_key] = st.session_state.get(folder_key, False)
            
            if folder_key not in st.session_state:
                st.session_state[folder_key] = self._checkbox_states[folder_key]
            
            if parent_selected and not st.session_state[folder_key]:
                st.session_state[folder_key] = True
            
            folder_selected = st.checkbox(
                "Select all", 
                key=folder_key,
                value=st.session_state.get(folder_key, False),
                on_change=self._folder_checkbox_callback,
                args=(node, folder_key, current_path, search_query)
            )
            
            for child in node.iter_children_sorted():
                if not self._node_matches_search(child, search_query):
                    continue
                
                self._render_node(
                    child,
                    level=level + 1,
                    parent_key=f"{parent_key}/{node.name}" if parent_key else node.name,
                    parent_selected=parent_selected or folder_selected,
                    search_query=search_query,
                    container=st,
                )
    
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
                self._set_files_under_node(root, global_selected, "root", search_query)
        
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
                parent_selected=global_selected,
                search_query=search_query,
                container=container,
            )
        
        container.caption(f"***{len(self.selected_files)}** files selected")
        return sorted(self.selected_files)
