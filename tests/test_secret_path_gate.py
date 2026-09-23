"""Unit tests for the secret-path gate and exclusion reasons (ADR-0016).

Borrowed from OCR's default_secret_patterns.json + isSecretEnvPath, with
additions (*.pem, *.key, credentials.json, secrets.yaml).  All checks are
pure path-string tests — no file content is ever read.
"""

from codewiki.mcp.tools.change_analysis import (
    _binary_paths_from_diff,
    _is_secret_path,
)


class TestSecretPathGate:
    def test_exact_names_any_depth(self):
        assert _is_secret_path(".npmrc")
        assert _is_secret_path("config/.npmrc")
        assert _is_secret_path("deploy/.pypirc")

    def test_ssh_private_keys(self):
        assert _is_secret_path(".ssh/id_rsa")
        assert _is_secret_path(".ssh/id_ed25519")
        assert _is_secret_path("home/user/.ssh/id_ecdsa")

    def test_ssh_dir_covers_everything(self):
        assert _is_secret_path(".ssh/known_hosts_config")
        assert _is_secret_path("a/b/.ssh/anything")

    def test_env_family(self):
        assert _is_secret_path(".env")
        assert _is_secret_path(".env.local")
        assert _is_secret_path(".env.production")

    def test_env_templates_exempt(self):
        assert not _is_secret_path(".env.example")
        assert not _is_secret_path(".env.sample")
        assert not _is_secret_path(".env.template")

    def test_case_insensitive(self):
        assert _is_secret_path(".ENV")
        assert _is_secret_path("Config/.NPMRC")
        assert _is_secret_path("certs/Server.PEM")

    def test_suffix_matches(self):
        assert _is_secret_path("certs/server.pem")
        assert _is_secret_path("keys/api.key")

    def test_added_patterns(self):
        assert _is_secret_path("gcloud/credentials.json")
        assert _is_secret_path("k8s/secrets.yaml")

    def test_not_secret(self):
        assert not _is_secret_path("src/main.py")
        assert not _is_secret_path("docs/README.md")
        assert not _is_secret_path("config/settings.py")
        assert not _is_secret_path("")

    def test_windows_backslash_normalized(self):
        assert _is_secret_path("config\\.npmrc")


class TestBinaryPathsFromDiff:
    def test_extracts_binary_paths(self):
        diff = (
            "diff --git a/logo.png b/logo.png\n"
            "index 123..456 100644\n"
            "Binary files a/logo.png and b/logo.png differ\n"
            "diff --git a/src/a.py b/src/a.py\n"
            "@@ -1 +1 @@\n"
            "-old\n"
            "+new\n"
        )
        assert _binary_paths_from_diff(diff) == {"logo.png"}

    def test_no_binary_lines(self):
        assert _binary_paths_from_diff("diff --git a/x.py b/x.py\n") == set()


class TestGateOrdering:
    """ADR-0016 f1 regression: secret/binary gates must run BEFORE _ext filter.

    .env (no suffix) / .pem / .png are not in _SRC_EXTS — if the extension
    filter ran first, these files would be silently dropped and never appear
    in `excluded` with a reason.
    """

    def test_secret_gate_records_despite_ext_filter(self, tmp_path):
        import subprocess

        repo = tmp_path / "r"
        repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True)
        (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
        (repo / ".env").write_text("TOKEN=abc\n", encoding="utf-8")
        (repo / "server.pem").write_text("-----BEGIN\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "init"], cwd=repo, check=True)
        (repo / ".env").write_text("TOKEN=xyz\n", encoding="utf-8")
        (repo / "server.pem").write_text("-----END\n", encoding="utf-8")
        (repo / "a.py").write_text("x = 2\n", encoding="utf-8")

        from codewiki.mcp.tools.change_analysis import collect_git_changes

        out = collect_git_changes(str(repo))
        excluded = {e["path"]: e["reason"] for e in out["excluded"]}
        assert excluded.get(".env") == "secret"
        assert excluded.get("server.pem") == "secret"
        assert any(c.path == "a.py" for c in out["changes"])


class TestUntrackedRendering:
    """ADR-0016 f2 regression: untracked files must render as readable lines,
    not a per-character stream (join over str instead of list)."""

    def test_untracked_join_regression(self):
        # Direct unit check of the fixed code path: by_file values must be lists.
        import inspect

        from codewiki.mcp.tools import review_changes as rc

        src = inspect.getsource(rc._build_changed_sources)
        assert "by_file[rel] = header + body" not in src
        assert "by_file.setdefault(rel, []).append(header + body)" in src
