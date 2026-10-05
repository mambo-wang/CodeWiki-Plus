"""`get_prompt` 工具通道服务 registry 工作流提示词（ADR-0017 薄壳契约的落地）。

背景：命令薄壳与 AGENTS.md 指示 Agent 调
``get_prompt(name="task-workflow", arguments={"repo_path": "."})``，但工具通道的
真参数是 ``prompt_type``，枚举只收模板类名字。只暴露 MCP 工具、没有
``prompts/get`` 通道的宿主（Qoder 系实测）照指引调用会被 schema 直接挡掉，
工作流全文取不到。修法：工具通道接住 registry 工作流名。

覆盖：
  - name=工作流名 → 返回全文（workflow=True）；
  - prompt_type=工作流名 / 下划线写法 → 同样接住（Agent 混用两种写法是常态）；
  - 平铺参数（repo_path / action / name 等）转发进工作流构建器，嵌套 arguments 优先；
  - 同名冲突时模板类优先（code_analysis vs code-analysis）；
  - schema 的 enum 与工作流名不漂移；
  - 未知名字返回两份可用清单而不是抛栈。
"""

from __future__ import annotations

import json
import os

from codewiki.mcp.prompts import _PROMPT_REGISTRY, _WORKFLOW_PROMPTS, workflow_prompt_names
from codewiki.mcp.session import SessionStore
from codewiki.mcp.tools.prompt_server import _PROMPT_CATALOG, handle_get_prompt


def _call(**arguments) -> dict:
    return json.loads(handle_get_prompt(arguments, SessionStore()))


def test_tool_channel_serves_workflow_by_name():
    res = _call(name="task-workflow", arguments={"repo_path": "."})
    assert res.get("workflow") is True
    assert "关联任务" in res["content"]


def test_tool_channel_accepts_prompt_type_and_underscore_spelling():
    for kwargs in ({"prompt_type": "team-memory-hook"}, {"name": "team_memory_hook"}):
        res = _call(arguments={"action": "status", "repo_path": "."}, **kwargs)
        assert res.get("workflow") is True, kwargs
        assert "--status" in res["content"]


def test_flat_params_reach_workflow_builders():
    # 宿主常把参数平铺在工具入参上：repo_path 退回 cwd 会指向别的仓库，
    # action 丢了则静默渲染成默认正文——两种静默错路都得拦住。
    repo = os.path.join(os.getcwd(), "tmp", "wired-repo")
    res = _call(name="team-memory-hook", repo_path=repo)
    assert res.get("workflow") is True
    assert os.path.normpath(repo) in res["content"]

    status = _call(name="team-memory-hook", action="status", repo_path=repo)
    assert "决策模板" in status["content"]
    # 判别式本身要可靠：默认正文（不传 action）不该含 status 档独有的字样
    assert "决策模板" not in _call(name="team-memory-hook", repo_path=repo)["content"]
    # 嵌套值优先于平铺同名键
    nested = _call(
        name="team-memory-hook",
        arguments={"action": "status"},
        action="enable",
        repo_path=repo,
    )
    assert "决策模板" in nested["content"]


def test_template_prompts_keep_priority_on_name_collisions():
    res = _call(prompt_type="code_analysis")
    assert res.get("workflow") is None
    assert res["prompt_type"] == "code_analysis"
    assert "content" in res
    # 连字符写法才是工作流通道——两者是不同内容，不能混为一谈
    wf = _call(name="code-analysis")
    assert wf.get("workflow") is True


def test_prompt_type_wins_and_flat_name_is_a_workflow_arg():
    # `name` 是 prompt_type 的别名，但 remove-workspace-repo 自己有个必填参数叫 name：
    # prompt_type 已给出标识符时，平铺的 name 必须归构建器，不能被当成标识符吃掉。
    res = _call(prompt_type="remove-workspace-repo", name="svc-a", workspace_path=".")
    assert res.get("workflow") is True
    assert "svc-a" in res["content"]


def test_missing_name_returns_both_available_lists():
    res = _call()
    assert "prompt_type" in res["error"]
    assert res["available_types"] == list(_PROMPT_CATALOG.keys())
    assert res["available_workflows"] == workflow_prompt_names()


def test_unknown_name_lists_workflows_too():
    res = _call(name="no-such-workflow")
    assert "Unknown prompt_type" in res["error"]
    assert "task-workflow" in res["available_workflows"]


def test_workflow_names_registered_and_schematised():
    # registry 与渲染表同源：新增工作流忘了挂 handler 会被这条拦住
    assert set(_WORKFLOW_PROMPTS) == {m["name"] for m in _PROMPT_REGISTRY}
    from codewiki.mcp.registry import REGISTRY

    schema = REGISTRY["get_prompt"].schema.inputSchema
    enum = schema["properties"]["prompt_type"]["enum"]
    for name in workflow_prompt_names():
        assert name in enum
    for tpl in _PROMPT_CATALOG:
        assert tpl in enum
    # name/arguments 是薄壳写法的入口；required 清空后两者至少要传一个（由 handler 判）
    assert {"name", "arguments"} <= set(schema["properties"])
    assert schema["required"] == []
