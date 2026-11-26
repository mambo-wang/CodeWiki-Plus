import asyncio
import os
import re
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Tuple
import logging
import tiktoken


logger = logging.getLogger(__name__)


# PythonMonkey (used by mermaid_parser.parse_mermaid_py) binds its JS engine
# to the thread that first imported it — typically the main thread at module
# load time. The caw backend dispatches MCP tool calls on a FastMCP
# daemon-thread event loop, where parse_mermaid_py raises
# "cannot find a running Python event-loop". Recording the main loop here
# lets validate_single_diagram marshal the call back via
# asyncio.run_coroutine_threadsafe so PythonMonkey finds its home loop.
_main_loop: "asyncio.AbstractEventLoop | None" = None
_main_loop_thread_ident: int | None = None


def set_main_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _main_loop, _main_loop_thread_ident
    _main_loop = loop
    _main_loop_thread_ident = threading.get_ident()


# ------------------------------------------------------------
# ---------------------- Complexity Check --------------------
# ------------------------------------------------------------


def is_complex_module(components: dict[str, any], core_component_ids: list[str]) -> bool:
    files = set()
    for component_id in core_component_ids:
        if component_id in components:
            files.add(components[component_id].file_path)

    result = len(files) > 1

    return result


# ------------------------------------------------------------
# ---------------------- Token Counting ---------------------
# ------------------------------------------------------------

enc = tiktoken.encoding_for_model("gpt-4")


def count_tokens(text: str) -> int:
    """
    Count the number of tokens in a text.
    """
    length = len(enc.encode(text))
    # logger.debug(f"Number of tokens: {length}")
    return length


# ------------------------------------------------------------
# ---------------------- Mermaid Validation -----------------
# ------------------------------------------------------------


@dataclass(frozen=True)
class _DiagramResult:
    status: Literal["valid", "invalid", "unavailable"]
    message: str = ""


def _is_parse_error(message: str) -> bool:
    return bool(
        re.search(r"parse error|lexical error|syntax error|no diagram type detected", message, re.I)
    )


def _diagram_message(message: str, diagram_num: int, line_start: int) -> str:
    message = re.sub(
        r"line (\d+)",
        lambda match: f"line {line_start + int(match.group(1))}",
        message,
    )
    return f"Diagram {diagram_num}: {message}"


async def validate_mermaid_diagrams(md_file_path: str, relative_path: str) -> str:
    """验证文件中的 Mermaid 图，并区分语法错误与校验不可用。"""
    try:
        file_path = Path(md_file_path)
        if not file_path.exists():
            return f"Error: File '{md_file_path}' does not exist"

        content = file_path.read_text(encoding="utf-8")
        mermaid_blocks = extract_mermaid_blocks(content)
        if not mermaid_blocks:
            return "No mermaid diagrams found in the file"

        errors = []
        unavailable = []
        for i, (line_start, diagram_content) in enumerate(mermaid_blocks, 1):
            result = await _validate_diagram(diagram_content)
            if result.status == "invalid":
                errors.append("\n" + _diagram_message(result.message, i, line_start))
            elif result.status == "unavailable":
                unavailable.append(
                    "\nWarning: Mermaid validation unavailable: "
                    + _diagram_message(result.message, i, line_start)
                )

        if errors:
            return (
                "Mermaid syntax errors found in file: "
                + relative_path
                + "\n"
                + "".join(errors + unavailable)
            )
        if unavailable:
            return (
                "Mermaid validation unavailable for file: "
                + relative_path
                + "\n"
                + "".join(unavailable)
            )
        return "All mermaid diagrams in file: " + relative_path + " are syntax correct"
    except Exception as e:
        return f"Error processing file: {str(e)}"


def auto_fix_mermaid_blocks(content: str) -> Tuple[str, List[str]]:
    """Apply mechanical auto-fixes to common Mermaid syntax errors.

    Returns (fixed_content, fixes) where *fixes* is a list of human-readable
    description strings (empty if nothing was changed).

    Fix rules:
    1. Multi-node one-liner: ``A[label] B[label]`` → split into two lines.
       ``A --> B`` is valid and left untouched.
    2. Unquoted labels with special chars: ``A[{id}]`` → ``A["{id}"]``.
    3. Unquoted CJK subgraph titles: ``subgraph 中文`` → ``subgraph "中文"``.
    """
    fixes: List[str] = []
    lines = content.split("\n")
    result_lines: List[str] = []
    in_mermaid = False

    for line in lines:
        stripped = line.strip()

        # Track mermaid block boundaries
        if stripped == "```mermaid" or stripped.startswith("```mermaid"):
            in_mermaid = True
            result_lines.append(line)
            continue
        if in_mermaid and stripped == "```":
            in_mermaid = False
            result_lines.append(line)
            continue

        if not in_mermaid:
            result_lines.append(line)
            continue

        # --- Inside a Mermaid block: apply fixes line-by-line ---

        # Skip 'click' directives — semantic issue, left for the validator.
        if stripped.startswith("click "):
            result_lines.append(line)
            continue

        # Rule 3: Quote CJK subgraph titles
        m = re.match(r"^(\s*subgraph\s+)([\u4e00-\u9fff][^\"]*?)$", line)
        if m and not m.group(2).strip().startswith('"'):
            title = m.group(2).strip()
            line = f'{m.group(1)}"{title}"'
            fixes.append(f'Quoted CJK subgraph title: "{title}"')

        # Rule 2: Quote labels containing { } inside [ ] that aren't already quoted
        # Matches A[xxx{yyy}zzz] but not A["..."] or A{label} (rhombus shape)
        def _quote_brace_label(mo: re.Match) -> str:
            prefix, label = mo.group(1), mo.group(2)
            if label.startswith('"'):
                return mo.group(0)  # already quoted
            fixes.append(f"Quoted label with curly braces: {label[:30]}")
            return f'{prefix}"{label}"]'

        line = re.sub(
            r"(\w\[)([^\]]*[{}][^\]]*)\]",
            _quote_brace_label,
            line,
        )

        # Rule 1: Split multi-node one-liners.
        # Detect ] followed by whitespace and another node-start (word + [ or ( ),
        # but NOT when --, -, ., ==, --> follows (that's an edge, which is valid).
        if "]" in line:
            # Preserve original indentation for split parts
            indent = re.match(r"^(\s*)", line).group(1)
            # Find positions where a ] is followed by space + identifier + [ or (
            # but not preceded by an edge arrow
            parts = [line]
            while True:
                m = re.search(r"\](\s+)(\w[\w]*)\s*[\[\(]", parts[-1])
                if not m:
                    break
                # Check the text between ] and the next node — reject if it's an edge
                between = m.group(1)
                if re.search(r"(-->|--|-|->|==|\.->|\.\.)", between.strip()):
                    break
                # Split: everything up to and including ] stays, rest goes to new line
                split_pos = m.start() + 1  # right after the ]
                parts.append(indent + parts[-1][split_pos:].strip())
                parts[-2] = parts[-2][:split_pos].rstrip()
                fixes.append("Split multi-node one-liner into separate lines")
            if len(parts) > 1:
                result_lines.extend(parts)
                continue

        result_lines.append(line)

    fixed_content = "\n".join(result_lines)
    return fixed_content, fixes


def extract_mermaid_blocks(content: str) -> List[Tuple[int, str]]:
    """
    Extract all mermaid code blocks from markdown content.

    Returns:
        List of tuples containing (line_number, diagram_content)
    """
    mermaid_blocks = []
    lines = content.split("\n")
    i = 0

    while i < len(lines):
        line = lines[i].strip()

        # Look for mermaid code block start
        if line == "```mermaid" or line.startswith("```mermaid"):
            start_line = i + 1
            diagram_lines = []
            i += 1

            # Collect lines until we find the closing ```
            while i < len(lines):
                if lines[i].strip() == "```":
                    break
                diagram_lines.append(lines[i])
                i += 1

            if diagram_lines:  # Only add non-empty diagrams
                diagram_content = "\n".join(diagram_lines)
                mermaid_blocks.append((start_line, diagram_content))

        i += 1

    return mermaid_blocks


# PythonMonkey 1.3.1 only supports Python 3.8–3.11. On 3.12+ it still imports,
# but its SpiderMonkey cleanup runs on the wrong thread during _Py_Finalize and
# segfaults at interpreter shutdown (macOS crash dialog after a successful run).
# Skip it proactively so SpiderMonkey is never loaded into the process.
_PYTHONMONKEY_BROKEN = sys.version_info >= (3, 12)

# mermaid-py spawns a Node.js subprocess that can hang indefinitely (e.g. when
# Node.js is missing or the mermaid CLI is misconfigured).  Enabled by default;
# set MERMAID_VALIDATE=0 to disable.
_MERMAID_PY_BROKEN = os.environ.get("MERMAID_VALIDATE", "1") == "0"
_MERMAID_PY_PROBED = True  # Skip probing — rely on env var


async def _try_pythonmonkey_parse(diagram_content: str) -> str | None:
    """Attempt to parse via PythonMonkey/mermaid-parser-py.

    Returns the extracted parse-error message, "" on success, or None when
    PythonMonkey itself is unusable (broken JS event loop binding on
    Python 3.13+) so the caller can fall back to mermaid-py.
    """
    global _PYTHONMONKEY_BROKEN
    if _PYTHONMONKEY_BROKEN:
        return None

    import os

    try:
        from mermaid_parser.parser import parse_mermaid_py
    except Exception:
        _PYTHONMONKEY_BROKEN = True
        return None

    old_stderr = sys.stderr
    sys.stderr = open(os.devnull, "w")
    try:
        if (
            _main_loop is not None
            and _main_loop.is_running()
            and threading.get_ident() != _main_loop_thread_ident
        ):
            fut = asyncio.run_coroutine_threadsafe(parse_mermaid_py(diagram_content), _main_loop)
            await asyncio.wrap_future(fut)
        else:
            await parse_mermaid_py(diagram_content)
        return ""
    except Exception as e:
        error_str = str(e)
        # PythonMonkey 1.3.1 only supports Python 3.8-3.11; on newer Pythons
        # every JS call raises this. Latch the failure once so subsequent
        # diagrams skip the broken path and go straight to mermaid-py.
        if "cannot find a running Python event-loop" in error_str:
            _PYTHONMONKEY_BROKEN = True
            return None
        match = re.search(r"Error:(.*?)(?=Stack Trace:|$)", error_str, re.DOTALL)
        if match and _is_parse_error(match.group(0)):
            return match.group(0).strip()
        # Unknown error from the JS parser — fall back rather than surface it.
        return None
    finally:
        sys.stderr.close()
        sys.stderr = old_stderr


def _remote_result(status_code: int, body: str) -> _DiagramResult:
    if 200 <= status_code < 300:
        return _DiagramResult("valid")
    if status_code in (400, 422) and _is_parse_error(body):
        return _DiagramResult("invalid", body)
    return _DiagramResult("unavailable", f"HTTP {status_code}: {body[:500]}")


def _parse_via_mermaid_py(diagram_content: str) -> _DiagramResult:
    """通过 mermaid-py 的 HTTP 响应区分有效、语法错误与服务不可用。"""
    import mermaid as md

    try:
        diagram = md.Mermaid(diagram_content)
    except Exception as e:
        if isinstance(e, getattr(md, "MermaidError", ())):
            status_code = getattr(e, "status_code", None)
            if isinstance(status_code, int):
                return _remote_result(status_code, getattr(e, "response_text", str(e)))
        return _DiagramResult("unavailable", str(e))

    checked_response = False
    for name in ("svg_response", "img_response"):
        response = getattr(diagram, name, None)
        if response is None:
            continue
        checked_response = True
        status_code = getattr(response, "status_code", None)
        if not isinstance(status_code, int):
            return _DiagramResult("unavailable", "renderer returned no HTTP response")
        result = _remote_result(status_code, response.text)
        if result.status != "valid":
            return result
    if not checked_response:
        return _DiagramResult("unavailable", "renderer returned no HTTP response")
    return _DiagramResult("valid")


def _run_in_daemon_thread(fn, *args) -> asyncio.Future:
    """在 daemon 线程执行阻塞调用，避免超时后解释器退出被永久 join。"""
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def _set(setter, value):
        if not future.done():
            setter(value)

    def _worker():
        try:
            setter, value = future.set_result, fn(*args)
        except BaseException as e:
            setter, value = future.set_exception, e
        try:
            loop.call_soon_threadsafe(_set, setter, value)
        except RuntimeError:
            pass

    threading.Thread(target=_worker, daemon=True).start()
    return future


async def _validate_diagram(diagram_content: str) -> _DiagramResult:
    global _MERMAID_PY_BROKEN
    for line in diagram_content.split("\n"):
        if line.strip().startswith("click "):
            return _DiagramResult(
                "invalid",
                "Interactive 'click' directive is not allowed in documentation diagrams.",
            )

    core_error = await _try_pythonmonkey_parse(diagram_content)
    if core_error is not None:
        if not core_error:
            return _DiagramResult("valid")
        if _is_parse_error(core_error):
            return _DiagramResult("invalid", core_error)
    if _MERMAID_PY_BROKEN:
        return _DiagramResult("unavailable", "remote validation disabled or previously timed out")
    try:
        return await asyncio.wait_for(
            _run_in_daemon_thread(_parse_via_mermaid_py, diagram_content),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        _MERMAID_PY_BROKEN = True
        logger.warning("Mermaid validation timed out (15s); skipping further remote validation")
        return _DiagramResult("unavailable", "remote renderer timed out after 15s")
    except Exception as e:
        return _DiagramResult("unavailable", str(e))


async def validate_single_diagram(diagram_content: str, diagram_num: int, line_start: int) -> str:
    """保留字符串接口：仅有效结果返回空串，不可用结果显式告警。"""
    result = await _validate_diagram(diagram_content)
    if result.status == "valid":
        return ""
    message = _diagram_message(result.message, diagram_num, line_start)
    if result.status == "unavailable":
        return "Warning: Mermaid validation unavailable: " + message
    return message


if __name__ == "__main__":
    # Test with the provided file
    import asyncio

    test_file = "output/docs/SWE_agent-docs/agent_hooks.md"
    result = asyncio.run(validate_mermaid_diagrams(test_file, "agent_hooks.md"))
    print(result)
