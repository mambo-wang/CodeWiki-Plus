"""Infrastructure scanner — docker-compose, Kubernetes, .env, application.yml.

Parses deployment configuration to discover service names, ports, and
inter-service dependencies that complement Route-based matching.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class InfraServiceInfo:
    """Minimal service info extracted from infrastructure configs."""

    def __init__(
        self,
        name: str,
        ports: List[int] = None,
        depends_on: List[str] = None,
        env_vars: Dict[str, str] = None,
        source: str = "",
        source_path: str = "",
    ):
        self.name = name
        self.ports = ports or []
        self.depends_on = depends_on or []
        self.env_vars = env_vars or {}
        self.source = source  # "docker-compose", "k8s", "env"
        # Workspace-relative path of the config file this service came from
        # (POSIX separators). Relative so attribution survives workspace
        # moves; lets remove_workspace_repo filter services per owning repo.
        self.source_path = source_path

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "ports": self.ports,
            "depends_on": self.depends_on,
            "env_vars": self.env_vars,
            "source": self.source,
            "source_path": self.source_path,
        }


class InfraScanner:
    """Scan a workspace directory for infrastructure configuration files."""

    def __init__(self, workspace_path: str):
        self.workspace_path = Path(workspace_path)
        self.services: Dict[str, InfraServiceInfo] = {}
        self.service_urls: Dict[str, str] = {}  # service_name → base URL

    def scan(self) -> Dict[str, InfraServiceInfo]:
        """Run all scanners and return the merged service map."""
        self._scan_docker_compose()
        self._scan_env_files()
        self._scan_application_yml()
        return self.services

    # ---- docker-compose.yml ----

    def _scan_docker_compose(self):
        """Parse docker-compose.yml / docker-compose.yaml files."""
        for pattern in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
            for f in self.workspace_path.rglob(pattern):
                self._parse_compose_file(f)

    def _parse_compose_file(self, path: Path):
        try:
            import yaml

            data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
        except ImportError:
            logger.debug("PyYAML not available, skipping docker-compose parsing")
            return
        except Exception as e:
            logger.warning("Failed to parse %s: %s", path, e)
            return

        if not isinstance(data, dict):
            return
        services = data.get("services", {})
        if not isinstance(services, dict):
            return

        for svc_name, svc_config in services.items():
            if not isinstance(svc_config, dict):
                continue

            # Ports
            ports: List[int] = []
            raw_ports = svc_config.get("ports", [])
            if isinstance(raw_ports, list):
                for p in raw_ports:
                    p_str = str(p)
                    # "8080:80" → host port 8080
                    if ":" in p_str:
                        try:
                            ports.append(int(p_str.split(":")[0]))
                        except (ValueError, IndexError):
                            pass
                    else:
                        try:
                            ports.append(int(p_str))
                        except ValueError:
                            pass

            # depends_on
            depends_on: List[str] = []
            raw_deps = svc_config.get("depends_on", [])
            if isinstance(raw_deps, list):
                depends_on = [str(d) for d in raw_deps]
            elif isinstance(raw_deps, dict):
                depends_on = list(raw_deps.keys())

            # Environment variables
            env_vars: Dict[str, str] = {}
            raw_env = svc_config.get("environment", [])
            if isinstance(raw_env, list):
                for item in raw_env:
                    item_str = str(item)
                    if "=" in item_str:
                        k, _, v = item_str.partition("=")
                        env_vars[k.strip()] = v.strip()
            elif isinstance(raw_env, dict):
                env_vars = {str(k): str(v) for k, v in raw_env.items()}

            info = InfraServiceInfo(
                name=svc_name,
                ports=ports,
                depends_on=depends_on,
                env_vars=env_vars,
                source="docker-compose",
                source_path=path.relative_to(self.workspace_path).as_posix(),
            )
            self.services[svc_name] = info

            # Derive service URL from first port
            if ports:
                self.service_urls[svc_name] = f"http://{svc_name}:{ports[0]}"

    # ---- .env files ----

    def _scan_env_files(self):
        """Scan .env files for SERVICE_URL patterns."""
        for f in self.workspace_path.rglob(".env"):
            # Skip node_modules and similar
            parts = f.parts
            if any(skip in parts for skip in ("node_modules", ".venv", "venv", ".git")):
                continue
            self._parse_env_file(f)
        for f in self.workspace_path.rglob(".env.*"):
            if f.name.endswith((".example", ".template", ".sample")):
                continue
            self._parse_env_file(f)

    def _parse_env_file(self, path: Path):
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return

        url_pattern = re.compile(
            r"^(\w*(?:SERVICE|API|URL|HOST|ENDPOINT)\w*)\s*=\s*(.+?)$",
            re.MULTILINE | re.IGNORECASE,
        )
        for m in url_pattern.finditer(content):
            key = m.group(1).strip()
            value = m.group(2).strip().strip('"').strip("'")
            # Extract service name from key: ORDER_SERVICE_URL → order-service
            svc_name = self._extract_service_name_from_key(key)
            if svc_name:
                self.service_urls[svc_name] = value

    def _extract_service_name_from_key(self, key: str) -> Optional[str]:
        """ORDER_SERVICE_URL → order-service, API_GATEWAY_HOST → api-gateway."""
        key = key.upper()
        for suffix in ("_URL", "_HOST", "_ENDPOINT", "_API"):
            if key.endswith(suffix):
                name = key[: -len(suffix)]
                return name.lower().replace("_", "-")
        return None

    # ---- application.yml (Spring Boot) ----

    def _scan_application_yml(self):
        """Scan application.yml / application.yaml for service URLs."""
        for pattern in ("application.yml", "application.yaml", "application.properties"):
            for f in self.workspace_path.rglob(pattern):
                parts = f.parts
                if any(
                    skip in parts
                    for skip in ("node_modules", ".venv", "venv", ".git", "target", "build")
                ):
                    continue
                self._parse_spring_config(f)

    def _parse_spring_config(self, path: Path):
        if path.suffix in (".yml", ".yaml"):
            try:
                import yaml

                data = yaml.safe_load(path.read_text(encoding="utf-8", errors="replace"))
            except ImportError:
                return
            except Exception:
                return
            if isinstance(data, dict):
                self._extract_urls_from_dict(data, prefix="")
        elif path.suffix == ".properties":
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                return
            url_pattern = re.compile(
                r"^.*?(?:service|api|url|host|endpoint).*?=(.+?)$",
                re.MULTILINE | re.IGNORECASE,
            )
            for m in url_pattern.finditer(content):
                value = m.group(1).strip()
                if value.startswith("http"):
                    # Try to extract service name from URL
                    svc_name = self._extract_service_from_url(value)
                    if svc_name:
                        self.service_urls[svc_name] = value

    def _extract_urls_from_dict(self, data: Dict, prefix: str):
        """Recursively extract URL values from a nested dict."""
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            full_key = f"{prefix}.{key}" if prefix else key
            if isinstance(value, str) and (
                value.startswith("http://") or value.startswith("https://")
            ):
                svc_name = self._extract_service_from_url(
                    value
                ) or self._extract_service_name_from_key(full_key)
                if svc_name:
                    self.service_urls[svc_name] = value
            elif isinstance(value, dict):
                self._extract_urls_from_dict(value, full_key)

    def _extract_service_from_url(self, url: str) -> Optional[str]:
        """http://order-service:8080 → order-service."""
        for scheme in ("https://", "http://"):
            if url.startswith(scheme):
                rest = url[len(scheme) :]
                host = rest.split(":")[0].split("/")[0]
                if host and not host.replace(".", "").isdigit():
                    return host
        return None


def scan_workspace_infra(workspace_path: str) -> Dict[str, InfraServiceInfo]:
    """Convenience function: scan and return services."""
    scanner = InfraScanner(workspace_path)
    return scanner.scan()
