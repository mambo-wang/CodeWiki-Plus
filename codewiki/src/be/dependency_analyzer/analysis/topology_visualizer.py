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
        """Return the full cross-service section (legacy, kept for compat)."""
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

    # ---- Overview-friendly concise section ----

    def render_overview_section(self, topology: WorkspaceTopology) -> str:
        """Return a concise cross-service section for overview.md.

        Contains only the Mermaid topology diagram and an aggregated
        per-service-pair summary.  Full API tables are excluded — they
        belong in the separate ``cross-service-api.md`` reference file.
        """
        parts: List[str] = []

        if topology.links:
            parts.append("## Service Topology\n")
            parts.append(self.generate_service_flowchart(topology))
            parts.append("")
            parts.append("## Cross-Service Summary\n")
            parts.append(self.render_aggregated_summary(topology))
            parts.append("")
        else:
            parts.append("## Cross-Service Relationships\n")
            parts.append("_No cross-service API calls detected automatically._")
            parts.append("")

        return "\n".join(parts)

    def render_aggregated_summary(self, topology: WorkspaceTopology) -> str:
        """Aggregate links by service pair: count + sample paths.

        Output format per pair:
            **client → server**: 12 calls (`GET /users`, `POST /orders`, …)
        """
        from collections import defaultdict

        pairs: dict[tuple[str, str], list[CrossServiceLink]] = defaultdict(list)
        for link in topology.links:
            pairs[(link.client_repo, link.server_repo)].append(link)

        lines: List[str] = []
        for (client, server), links in sorted(pairs.items()):
            # Pick up to 3 representative paths
            samples = []
            seen = set()
            for lk in links:
                sig = f"{lk.method or '?'} {lk.path}"
                if sig not in seen:
                    seen.add(sig)
                    samples.append(f"`{sig}`")
                if len(samples) >= 3:
                    break
            sample_str = ", ".join(samples)
            if len(seen) < len(links):
                sample_str += ", …"
            lines.append(f"- **{client} → {server}**: {len(links)} calls ({sample_str})")

        return "\n".join(lines) if lines else "_No matched links._"

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
        for link in sorted(topology.links, key=lambda link: (link.client_repo, link.path)):
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
            lines.append(f"| {method} | `{path}` | {route.repo_name} | {role} | {note} |")
        return "\n".join(lines)
