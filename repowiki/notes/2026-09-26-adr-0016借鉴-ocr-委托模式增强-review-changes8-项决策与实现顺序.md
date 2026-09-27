---
type: decision
title: ADR-0016：借鉴 OCR 委托模式增强 review_changes（8 项决策与实现顺序）
tags:
- codewiki
- decision
metadata:
  date: 2026-09-26
  confidence_level: weak
  source_session: 2364d2066b2946459fd01a6779ff9159
  related_modules:
  - review_changes
  - change_analysis
  - review_checklist
  - prompts
  severity: medium
  source_ref: conversations/conv-working_memory_content-The-following-is-the-existing-working-3-e09bcd.md
  scene: 借鉴 OCR 委托模式增强 review_changes
status: stable
author: iamwangbao-163-com
generated:
  by: codewiki/5.13.1
  at: 2026-09-26 13:35:29+00:00
stale_after: '2027-09-26'
origin: conversation
verified:
- by: human:wangbao
  at: '2026-09-26T13:57:58Z'
---

## 背景

CodeWiki 的 `review_changes`（prepare→submit、零 LLM 的确定性装配）与 alibaba/open-code-review（OCR）的委托模式同属「工具做确定性簿记、推理在调用方」形态。对照 OCR 源码后确认可借鉴四项确定性工程：文件筛选门、排除原因标注、覆盖率校验、清单排除项；我们已有的四轴证据（spec/convention/module_knowledge/general）与影响面分析是 OCR 没有的底座，不照搬整体架构。

## 决策（grill-with-docs 两轮收敛）

1. **借鉴范围 = 委托形态 + prompt 增强**（Q1=B）：只借确定性工程，LLM 侧约束写进 `prompts.py`，不往工具里塞 LLM（Doctrine「工具不持模型」）。
2. **筛选门分层**（Q2=C）：密钥/二进制门放 `collect_git_changes`（普适安全，评审与影响面分析两个调用方统一受益）；vendor/体量门放 `review_changes` prepare（评审专属，影响面分析保持 vendor 语义）。
3. **密钥门**（Q7=B'、Q8=A、Q11=A）：OCR 10 条 glob + `.env` 家族（`.env.example/.sample/.template` 显式豁免）+ 补充 `*.pem/*.key/credentials.json/secrets.yaml`；独立纯函数 `_is_secret_path(path) -> bool` + 单测；大小写不敏感、纯路径判断不读文件内容；只读内置模式不读项目 YAML。
4. **排除原因**（Q3=A、Q9=A'、Q10=B）：prepare 输出加 `excluded: [{path, reason}]` 逐文件标注 + `excluded_summary` 分类汇总；枚举 secret/binary/noise/oversized；二进制文件丢弃但标注、不计覆盖率分母。
5. **覆盖率**（Q4=C、Q12=A'）：先软警告（submit 返回 `coverage_warnings.uncovered_files`，skipped 必须带原因否则视为未覆盖），下一版按数据决定是否硬化。
6. **清单排除项**（Q5=A+B）：内置清单 + 项目覆盖层 YAML 都支持 `exclusions` 字段（声明「该问题类型在什么条件下不该报」，如 `.pyi` 存根的未用导入不算问题、性能问题先确认热路径）。
7. **prompt 增强**（Q13=A''）：评审纪律强制段——覆盖率强制（每文件必有去向）、别停在第一个高危、行号锚定（findings 行号必须来自 diff 行号空间，报告前核对）、excluded 不读内容、secret 类排除在 summary 提醒。
8. **明确不做**：规则分组去重（清单仅 15 条无重复痛点）、`.m` 内容嗅探（无 MATLAB/ObjC 规则可路由）、OCR 完整模式 LLM 流水线（Plan/行号校准/事实核查/内存压缩——违反 Doctrine）。

## 实现顺序

密钥门 → 二进制标注 → vendor/体量门 → 覆盖率软警告 → 清单排除项 → prompt 增强。

## Rationale

OCR 是「favor precision over recall」且被验证的实现；我们只借缺失的确定性工程，不借推理责任；覆盖率等归因调优决策遵循「先实测计数再下结论」的 Doctrine。
