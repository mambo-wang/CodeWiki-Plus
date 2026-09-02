"""Migrate an existing repository to the team layout (Phase 1, D1).

Team-layout Phase 1 keeps rebuildable derived files out of git
(docs/团队化文件冲突治理与同步策略设计方案.md §5.1): every index/derived/
runtime file (wiki/index.md, .meta/*.json indexes, tasks/.index.json, ...)
has a local rebuild path, and committing it only creates merge conflicts in
team use.

For repositories initialized before this change those files are already
tracked; this command performs the one-time migration:

1. ``git rm --cached`` the still-tracked rebuildable files (files stay on
   disk, only the tracking is removed — nothing is deleted);
2. append the team-layout block to the repo-root .gitignore (idempotent);
3. print a summary and remind the user to review + commit the staged
   removals.

Safety properties: ``--dry-run`` shows what would happen without touching
the index or .gitignore; the command never commits and never deletes any
file from disk.
"""

from __future__ import annotations

from pathlib import Path

import click

from codewiki.cli.utils.errors import handle_error
from codewiki.mcp.tools.team_layout import (
    ensure_gitignore_entries,
    find_repo_root,
    list_tracked_rebuildables,
    untrack_files,
)


@click.command(name="migrate-team-layout")
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option("--dry-run", is_flag=True, default=False, help="Show planned actions only.")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    default=None,
    help=(
        "Wiki output directory (default: <repo>/repowiki). Pass the harness "
        "repowiki path for workspace-root migrations; the repo must contain it."
    ),
)
def migrate_team_layout_command(repo_path: str, dry_run: bool, output_dir: str | None) -> None:
    """Untrack rebuildable derived files (git rm --cached, files stay on disk)."""
    try:
        _run(repo_path, dry_run, output_dir)
    except Exception as e:  # pragma: no cover - defensive CLI boundary
        handle_error(e)


def _run(repo_path: str, dry_run: bool, output_dir_arg: str | None = None) -> None:
    repo_root = find_repo_root(Path(repo_path))
    if repo_root is None:
        click.secho(f"Not a git repository: {repo_path}", fg="red")
        raise SystemExit(2)

    # output_dir defaults to <repo>/repowiki (same convention as init_wiki);
    # a custom value (e.g. workspace/harness repowiki) must live inside the repo.
    if output_dir_arg:
        output_dir = Path(output_dir_arg).resolve()
        try:
            output_dir.relative_to(repo_root.resolve())
        except ValueError:
            click.secho(f"--output-dir must be inside the repository: {output_dir}", fg="red")
            raise SystemExit(2)
    else:
        output_dir = repo_root / "repowiki"
    if not output_dir.is_dir():
        click.secho(f"No wiki directory at {output_dir} — nothing to migrate.", fg="yellow")
        raise SystemExit(0)

    tracked = list_tracked_rebuildables(repo_root, output_dir)

    click.secho(f"Repository: {repo_root}", fg="blue", bold=True)
    click.echo()

    if tracked:
        click.secho("Tracked rebuildable files (will be untracked, NOT deleted):", fg="cyan")
        for rel in tracked:
            click.echo(f"  {rel}")
    else:
        click.echo("No rebuildable files are tracked — repository is already on the team layout.")

    click.echo()
    if dry_run:
        click.secho("[dry-run] No changes made.", fg="yellow")
        return

    untracked_ok = True
    if tracked:
        untracked_ok, staged = untrack_files(repo_root, tracked)
        if untracked_ok:
            click.secho(f"Untracked {len(staged)} file(s) via git rm --cached.", fg="green")
        else:
            click.secho("git rm --cached failed — index left untouched.", fg="red")

    changed, added = ensure_gitignore_entries(repo_root, output_dir)
    if changed:
        click.secho(f".gitignore updated (+{len(added)} entries).", fg="green")
    else:
        click.echo(".gitignore already contains the team-layout block.")

    click.echo()
    if untracked_ok:
        click.secho(
            "Next: review the staged removals (`git status`) and commit them. "
            "The files remain on disk and are rebuilt locally on demand "
            "(wiki/index.md on the next lint_wiki run, indexes on the next "
            "analyze/task operation).",
            fg="cyan",
        )
    else:
        raise SystemExit(1)
