def _clear_all_selections(self):
    """Clear all selections globally."""
    # Clear all file checkboxes
    for key in list(st.session_state.keys()):
        if key.startswith("file::"):
            st.session_state[key] = False
    
    # Clear all folder checkboxes
    for key in list(st.session_state.keys()):
        if key.startswith("folder::"):
            st.session_state[key] = False
    
    # Clear global checkbox
    global_key = "global::select_all"
    st.session_state[global_key] = False
    
    # Clear internal state
    self.selected_files.clear()
    self._checkbox_states.clear()

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
    
    # Global controls in columns
    col1, col2 = container.columns([3, 1])
    
    with col1:
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
    
    with col2:
        # Clear Selection button with callback
        if container.button("Clear All", key="global_clear_button", type="secondary", on_click=self._clear_all_selections):
            pass  # Callback handles everything
    
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
