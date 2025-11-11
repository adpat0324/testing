import streamlit as st
from typing import Dict, List, Optional

class FileTreeSelector:
    """Flat searchable file selector with a working Select All toggle."""

    def __init__(self, file_metadata: Dict[str, Dict], state_key: str = "fts"):
        self.file_metadata = file_metadata or {}
        self.state_key = state_key

        # All file paths
        self.options = sorted(self.file_metadata.keys(), key=str.lower)

        # Widget keys (allowed to modify inside callbacks)
        self.k_search = f"{state_key}_search"
        self.k_selectall = f"{state_key}_all"
        self.k_multiselect = f"{state_key}_ms"

        # Initialize widget state once
        st.session_state.setdefault(self.k_search, "")
        st.session_state.setdefault(self.k_selectall, False)
        st.session_state.setdefault(self.k_multiselect, [])

    # ----------------------------
    # CALLBACKS
    # ----------------------------

    def _toggle_select_all(self):
        """When Select All checkbox toggles, update the multiselect widget directly."""
        if st.session_state[self.k_selectall]:
            # Select ALL visible filtered items
            search = st.session_state[self.k_search].lower()
            filtered = [
                p for p in self.options
                if search in p.lower()
            ]
            st.session_state[self.k_multiselect] = filtered
        else:
            # Clear all selected
            st.session_state[self.k_multiselect] = []

    def _sync_selectall_to_multiselect(self, filtered_list: List[str]):
        """Automatically keeps Select All synced to multiselect content."""
        selected = st.session_state[self.k_multiselect]
        st.session_state[self.k_selectall] = (
            len(filtered_list) > 0 and set(selected) == set(filtered_list)
        )

    # ----------------------------
    # RENDER
    # ----------------------------

    def render(self, container: Optional[st.delta_generator.DeltaGenerator] = None,
               height: int = 300) -> List[str]:

        if container is None:
            container = st

        # SEARCH BAR
        search = container.text_input(
            "Search Documents",
            key=self.k_search,
            placeholder="Type to filter files…",
        ).lower()

        # FILTERED OPTIONS
        filtered = [
            p for p in self.options
            if search in p.lower()
        ]

        # SELECT ALL
        container.checkbox(
            "Select All (filtered)",
            key=self.k_selectall,
            on_change=self._toggle_select_all
        )

        # MULTISELECT LIST (searchable & scrollable automatically)
        selected = container.multiselect(
            "",
            options=filtered,
            key=self.k_multiselect,
        )

        # KEEP SELECT ALL IN SYNC
        self._sync_selectall_to_multiselect(filtered)

        container.caption(f"**{len(selected)} files selected**")

        return selected
