"""Backfill ``author`` on existing notes (Team-layout Phase 3, D16 follow-up).

New notes get ``author`` stamped automatically since aefdafe; notes created
before that carry none.  This one-time (but re-runnable / idempotent)
migration closes the gap so future multi-user governance (adoption stats,
promotion) sees provenance for the whole corpus.

Author resolution, in order:
1. ``--author <user_id>`` — explicit override for the whole run;
2. per-note git provenance — the author of the commit that CREATED the file
   (``git log --follow --diff-filter=A``), mapped through the git-name →
   user_id convention (``CODEWIKI_USER`` env, else git name, else login);
3. ``--default`` — fallback for notes with no git provenance (uncommitted
   local notes); without it they are reported and skipped, never guessed.

Writes go through ``KnowledgeStore.update_frontmatter`` (sidecar lock +
atomic write, preserves unknown keys) — same primitive confirm_note uses.
``--dry-run`` lists what would change without touching anything.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import click

from codewiki.cli.utils.errors import handle_error


def _git_creator_author(repo_root: Path, note_rel: str) -> str | None:
    """Git author name of the commit that created *note_rel*.

    Deliberately WITHOUT ``--follow``: it misbehaves on multi-file history
    (can resolve to an unrelated commit), and notes are never renamed —
    supersede creates a new file.  Single entry = the creation commit.
    """
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "--diff-filter=A",
                "--format=%an",
                "--",
                note_rel,
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
        )
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().splitlines()[-1].strip()
    except Exception:
        pass
    return None


def _iter_notes(output_dir: Path):
    """Yield (note_path, has_author) for frontmatter-carrying notes."""
    import yaml

    notes_dir = output_dir / "notes"
    if not notes_dir.is_dir():
        return
    for n in sorted(notes_dir.glob("*.md")):
        try:
            text = n.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end < 0:
            continue
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except Exception:
            continue
        if isinstance(fm, dict):
            yield n, bool(fm.get("author"))


@click.command(name="backfill-note-authors")
@click.argument("repo_path", type=click.Path(exists=True, file_okay=False), default=".")
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False),
    default=None,
    help="Wiki output directory (default: <repo>/repowiki).",
)
@click.option(
    "--author",
    "author_arg",
    default=None,
    help="Stamp this user_id on ALL notes (overrides git provenance).",
)
@click.option(
    "--default",
    "default_author",
    default=None,
    help="Fallback user_id for notes without git provenance (default: skip them).",
)
@click.option("--dry-run", is_flag=True, default=False, help="List planned changes only.")
def backfill_note_authors_command(
    repo_path: str,
    output_dir: str | None,
    author_arg: str | None,
    default_author: str | None,
    dry_run: bool,
) -> None:
    """Backfill ``author`` frontmatter on existing notes from git provenance."""
    try:
        _run(repo_path, output_dir, author_arg, default_author, dry_run)
    except Exception as e:  # pragma: no cover - defensive CLI boundary
        handle_error(e)


def _run(
    repo_path: str,
    output_dir_arg: str | None,
    author_arg: str | None,
    default_author: str | None,
    dry_run: bool,
) -> None:
    repo_root = Path(repo_path).resolve()
    output_dir = Path(output_dir_arg).resolve() if output_dir_arg else repo_root / "repowiki"

    to_stamp: list[tuple[Path, str]] = []  # (note, author)
    already: list[Path] = []
    skipped: list[tuple[Path, str]] = []  # (note, reason)

    for note, has_author in _iter_notes(output_dir):
        if has_author:
            already.append(note)
            continue
        if author_arg:
            to_stamp.append((note, author_arg))
            continue
        git_author = _git_creator_author(repo_root, note.relative_to(repo_root).as_posix())
        if git_author:
            to_stamp.append((note, git_author))
        elif default_author:
            to_stamp.append((note, default_author))
        else:
            skipped.append((note, "no git provenance and no --default given"))

    click.secho(
        f"Notes scanned: {len(already) + len(to_stamp) + len(skipped)}", fg="blue", bold=True
    )
    click.echo(f"  already have author: {len(already)}")
    click.echo(f"  to stamp:            {len(to_stamp)}")
    click.echo(f"  skipped:             {len(skipped)}")
    if skipped:
        for note, reason in skipped[:5]:
            click.echo(f"    - {note.name} ({reason})")
        if len(skipped) > 5:
            click.echo(f"    ... and {len(skipped) - 5} more")

    if dry_run:
        click.secho("[dry-run] No changes made.", fg="yellow")
        for note, author in to_stamp[:10]:
            click.echo(f"  would stamp: {author:<20} {note.name[:60]}")
        return

    from codewiki.src.store import KnowledgeStore

    ks = KnowledgeStore(output_dir)
    stamped = 0
    failures = 0
    for note, author in to_stamp:
        try:
            rel = note.relative_to(output_dir).as_posix()
            if ks.update_frontmatter(rel, author=author):
                stamped += 1
            else:
                failures += 1
        except Exception as e:
            failures += 1
            click.secho(f"  failed: {note.name}: {e}", fg="red")

    click.secho(f"Stamped author on {stamped} note(s).", fg="green")
    if failures:
        click.secho(f"{failures} note(s) failed — re-run to retry.", fg="red")
        raise SystemExit(1)
