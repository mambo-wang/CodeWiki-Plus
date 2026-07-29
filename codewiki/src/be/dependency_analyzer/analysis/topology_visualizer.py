"""Topology visualizer — generate Mermaid diagrams and Markdown tables.

Converts a ``WorkspaceTopology`` into human-readable documentation
suitable for embedding in workspace ``overview.md``.
"""
from __future__ import annotations

from typing import List

from codewiki.src.be.dependency_analyzer.models.cross_service import (
    CrossServiceLink,
    WorkspaceTopology,
)


class TopologyVisualizer:
    """Render a WorkspaceTopology as Mermaid + Markdown."""

    def render_all(self, topology: WorkspaceTopology) -> str:
        """Return the full cross-service section for overview.md."""
        parts: List[str] = []

        if topology.links:
            parts.append("## Service Topology\n")
            parts.append(self.generate_service_flowchart(topology))
            parts.append("")
            parts.append("## Cross-Service API Calls\n")
            parts.append(self.generate_route_table(topology))
            parts.append("")
        else:
            parts.append("## Cross-Service Relationships\n")
            parts.append("_No cross-service API calls detected automatically._")
            parts.append("")

        if topology.unmatched_routes:
            parts.append("## Unmatched Routes\n")
            parts.append(self.generate_unmatched_table(topology))
            parts.append("")

        return "\n".join(parts)

    # ---- Mermaid flowchart ----

    def generate_service_flowchart(self, topology: WorkspaceTopology) -> str:
        """Generate a Mermaid flowchart: services as nodes, API calls as edges."""
        lines = ["```mermaid", "flowchart LR"]

        # Collect unique edges: source_repo →|METHOD path| target_repo
        edge_labels: dict[tuple[str, str], list[str]] = {}
        for link in topology.links:
            key = (link.client_repo, link.server_repo)
            label = f"{link.method or '?'} {link.path}"
            if key not in edge_labels:
                edge_labels[key] = []
            edge_labels[key].append(label)

        # Sanitize repo names for Mermaid (no hyphens in node IDs)
        node_ids: dict[str, str] = {}
        for repo in topology.repos:
            safe = repo.replace("-", "_").replace(".", "_")
            node_ids[repo] = safe

        # Declare nodes
        for repo in topology.repos:
            nid = node_ids[repo]
            lines.append(f"    {nid}[{repo}]")

        # Edges
        for (src, tgt), labels in edge_labels.items():
            src_id = node_ids.get(src, src)
            tgt_id = node_ids.get(tgt, tgt)
            combined = "\\n".join(labels[:3])  # cap at 3 labels
            if len(labels) > 3:
                combined += f"\\n(+{len(labels) - 3} more)"
            lines.append(f"    {src_id} -->|{combined}| {tgt_id}")

        lines.append("```")
        return "\n".join(lines)

    # ---- Cross-service API table ----

    def generate_route_table(self, topology: WorkspaceTopology) -> str:
        """Generate a Markdown table of matched cross-service links."""
        lines = [
            "| Method | Path | Client Service | Client Function | Server Service | Server Function |",
            "|--------|------|----------------|-----------------|----------------|-----------------|",
        ]
        for link in sorted(topology.links, key=lambda l: (l.client_repo, l.path)):
            method = link.method or "—"
            path = link.path or "—"
            client_func = link.client_function or "—"
            server_func = link.server_function or "—"
            lines.append(
                f"| {method} | `{path}` | {link.client_repo} | `{client_func}` "
                f"| {link.server_repo} | `{server_func}` |"
            )
        return "\n".join(lines)

    # ---- Unmatched routes table ----

    def generate_unmatched_table(self, topology: WorkspaceTopology) -> str:
        """Generate a Markdown table of routes without a cross-service match."""
        lines = [
            "| Method | Path | Service | Role | Note |",
            "|--------|------|---------|------|------|",
        ]
        # Only show client unmatched (external API calls are interesting)
        for route in sorted(
            topology.unmatched_routes,
            key=lambda r: (r.repo_name, r.path),
        ):
            method = route.method or "—"
            path = route.path or "—"
            role = "Client" if route.role.value == "client" else "Server"
            note = ""
            if route.role.value == "client":
                note = "External API or unimplemented"
            else:
                note = "No client detected"
            lines.append(
                f"| {method} | `{path}` | {route.repo_name} | {role} | {note} |"
            )
        return "\n".join(lines)
