def _folder_checkbox_callback(self, node: FileNode, folder_key: str, current_path: str):
    """Callback for folder 'Select all' checkbox changes."""
    folder_selected = st.session_state[folder_key]
    self._checkbox_states[folder_key] = folder_selected
    
    # Apply change to all descendants
    self._set_files_under_node(node, folder_selected, current_path)

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
            on_change=self._folder_checkbox_callback,
            args=(node, folder_key, current_path)
        )
        
        # If unselecting, also clear all deeper folder checkboxes in state
        if not folder_selected:
            for child in node.children.values():
                if not child.is_file:
                    child_key = self._folder_checkbox_key(current_path, child.name)
                    st.session_state[child_key] = False
                    self._checkbox_states[child_key] = False
        
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
