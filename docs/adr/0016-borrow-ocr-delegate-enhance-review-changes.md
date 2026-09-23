# ADR-0016: 借鉴 OCR 委托模式增强 review_changes

- **状态**：已接受（2026-09-21，grill-with-docs 两轮拷问后拍板）
- **背景调研**：alibaba/open-code-review main 分支源码核对（v1.12.7），非文档站转述

## 背景

OCR（alibaba/open-code-review）委托模式与我们的 `review_changes` 同属「工具做确定性簿记、推理在调用方」形态。经源码核对，我们缺四样东西：文件筛选门、排除原因标注、覆盖率校验、清单排除项。OCR 有验证过的实现可借鉴。

关键事实：
- `collect_git_changes`（`change_analysis.py:208`）有两个调用方：`review_changes.py:595`（评审）和 `change_analysis.py:528`（影响面分析），筛选门分层必须考虑两者语义差异
- 我们 `change_analysis.py:146` 对 `Binary files` 行静默跳过，二进制文件以空变更形式留在结果里，无标注
- `_validate_report`（`review_changes.py:446`）只校验 findings 非空，不校验变更文件覆盖情况
- `review_checklist.py:60-80` 内置清单 15 条（10 all + 5 python），全是正向问题、零排除项

## 决策

### 1. 借鉴范围 = 委托形态 + prompt 增强（Q1=B）

只借确定性工程（筛选门、排除原因、覆盖率、清单排除项），LLM 侧约束写进 `prompts.py`，不往工具里塞 LLM。OCR 完整模式的 Plan/行号校准/事实核查流水线不借——违反 Doctrine「工具不持模型」。

### 2. 筛选门分层（Q2=C）

- **密钥/二进制门 → `collect_git_changes`**（普适安全，两个调用方统一受益）
- **vendor/体量门 → `review_changes` prepare**（评审专属，影响面分析保持原语义——vendor 文件变了，依赖它的代码确实受影响）

### 3. 密钥门模式（Q7=B'、Q8=A、Q8b=A'、Q11=A）

内置模式照搬 OCR（`default_secret_patterns.json` + `isSecretEnvPath`）并补充：
- OCR 的 10 条 glob：`.ssh/**`、`id_rsa/dsa/ecdsa/ed25519`、`.netrc/_netrc`、`.npmrc`、`.pypirc`、`.dockercfg`
- `.env` 家族（`.env.example/.sample/.template` 显式豁免）
- 补充：`**/credentials.json`（gcloud）、`**/*.pem`、`**/*.key`、`**/secrets.yaml`（K8s）
- 实现为独立纯函数 `_is_secret_path(path) -> bool`，大小写不敏感、纯路径判断不读内容
- 单测锁住：`.env.example` 豁免、大小写不敏感、`.ssh/` 目录匹配
- **密钥门只读内置模式**（`collect_git_changes` 保持纯 git 函数，不读 YAML）；项目自定义密钥模式走 `review_checklist` 覆盖层（评审专属）
- 影响面分析结果里密钥文件带 `secret: true` 标签（路径可见不构成泄漏——只输出路径/组件 ID 不输出内容；标签让调用方知情）

### 4. 排除原因逐文件标注（Q3=A、Q9=A'、Q10=B）

prepare 输出加 `excluded` 数组，逐文件带原因 + 分类汇总：

```json
{
  "excluded": [{"path": "logo.png", "reason": "binary"}],
  "excluded_summary": {"binary": 1, "noise": 3, "secret": 1, "oversized": 0}
}
```

- 原因枚举：`secret` | `binary` | `noise`（vendor/生成物/测试快照）| `oversized`（单文件 diff 超体量上限）
- 二进制文件**丢弃 + 标注**（不保留空条目——无法评审的东西不该出现在覆盖率要求里）
- `(path, status)` 双重身份规则**本轮不做**（「staged 删除 + untracked 重建」边缘 case 无现实痛点）

### 5. 覆盖率分阶段（Q4=C、Q12=A'）

- 本版：submit 返回加 `coverage_warnings: {uncovered_files: [path...]}`，软警告不 reject
- `skipped` 必须带原因，否则视为未覆盖（对齐 Doctrine「候选必有去向，排除必填原因」）
- 下一版按实测数据决定是否硬化为 reject

### 6. 清单排除项（Q5=A+B）

内置清单和项目覆盖层 YAML 都支持 `exclusions` 字段，声明「该问题类型在什么条件下不该报」。首批翻译 OCR 验证过的排除项：`.pyi` 存根的未用导入不算死代码、性能问题先确认热路径、并发问题须有并发调用证据。

### 7. prompt 增强（Q13=A''）

`prompts.py` 的 review prompt 增加约束：
- 覆盖率强制：每个变更文件必须有去向（reviewed / skipped+原因）
- 别找到第一个高危就停
- 行号锚定：findings 行号必须来自 diff 的行号空间，报告前用 git diff 核对
- 重申四轴裁决顺序 spec > convention > module_knowledge > general

### 8. 明确不做

- 规则分组去重（清单仅 15 条，无重复痛点）
- `.m` 扩展名嗅探（无 MATLAB/ObjC 规则可路由）
- OCR 完整模式的 LLM 流水线（违反 Doctrine）

## 后果

- **正面**：密钥泄漏防护（`.env`/私钥不再进评审包）、评审噪音降低、覆盖率可观测、清单表达力增强。
- **负面**：prepare 输出体积增大（excluded 明细）；`collect_git_changes` 新增纯函数依赖（保持不读 YAML 的性质）。
- **风险**：覆盖率软警告若被调用方忽略，硬化前需观察一版数据（Q4=C 的分阶段设计正是为此）。

## 实现顺序

1. 密钥门纯函数 + 单测（安全优先）
2. 二进制丢弃 + excluded 标注（`collect_git_changes` 层）
3. vendor/体量门 + prepare 输出装配（`review_changes` 层）
4. submit 覆盖率软警告
5. 清单排除项（内置 + 覆盖层）
6. prompt 增强
