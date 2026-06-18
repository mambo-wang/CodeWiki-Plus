## CodeWiki：用 AI 为代码仓库自动生成结构化文档的开源框架

对于任何一个开发者来说，理解一个陌生代码仓库都是一项挑战。无论是刚加入团队的新人、做代码审查的同事，还是想要复用开源项目的开发者，都需要面对"读代码"这道坎。而代码文档往往是稀缺资源——要么缺失，要么早已过时，与实际代码脱节。

CodeWiki 正是为了解决这个问题而生的开源项目。它由 FPT Software AI Center（FSoft）团队开发，已被 ACL 2026 收录，目标是自动为大规模代码仓库生成全面、结构化、架构感知的文档。项目开源地址：[https://github.com/FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki)

### 它解决了什么问题？

传统的代码文档工具大多只关注函数和类级别的 docstring 提取，例如 Sphinx、Javadoc 这类工具，它们能生成 API 参考文档，但无法回答更高层次的问题：这个项目的整体架构是什么？模块之间是如何协作的？数据流是怎样的？

与此同时，市面上也出现了一些 AI 驱动的代码文档工具，如 DeepWiki 等商业方案。但这些方案大多是闭源的，且在处理大型仓库时存在文档质量参差不齐、对多语言支持不足等问题。

CodeWiki 的定位很明确：做一个开源的、支持多语言的、能生成仓库级全景文档的框架，并且在文档质量上对标甚至超越商业方案。

### 核心设计理念

CodeWiki 的设计围绕三个核心思想展开。

第一个是**层次化分解（Hierarchical Decomposition）**。面对一个动辄数十万行代码的大型仓库，CodeWiki 不会一股脑地把所有代码喂给大模型，而是先通过 AST（抽象语法树）解析和依赖分析，将仓库拆解为模块、子模块、文件、类、函数等多层结构。这种分而治之的策略既降低了大模型的上下文压力，也让最终生成的文档具有清晰的层次感。

第二个是**多智能体协作（Multi-Agent Processing）**。CodeWiki 内部设计了多个专职 Agent，每个 Agent 负责不同层级或不同类型的文档生成任务。例如有的 Agent 负责分析模块间的依赖关系，有的负责总结某个类的职责，有的负责生成架构图。这些 Agent 各司其职、协同工作，最终将各自的输出汇总成一份完整的文档。

第三个是**多模态合成（Multi-Modal Synthesis）**。CodeWiki 生成的文档不仅仅是文字描述，还包括架构图、依赖关系图、模块树等可视化内容。文字与图表相结合，让读者既能从宏观上把握项目全貌，也能深入理解具体模块的实现细节。

### 支持的语言和模型

CodeWiki 目前支持 8 种主流编程语言：Python、Java、JavaScript、TypeScript、C、C++、C# 和 Kotlin。这个覆盖面已经涵盖了绝大多数企业和开源项目的技术栈。

在 LLM 后端方面，CodeWiki 提供了灵活的适配层，支持两种接入模式：API 模式支持 OpenAI 兼容接口（可对接 OpenAI、Azure OpenAI 及任意兼容服务）、Anthropic（Claude）、AWS Bedrock 等主流大模型服务；订阅模式则支持通过 Claude Code 和 Codex 的本地 CLI 运行，无需单独申请 API Key。开发者可以根据自己的偏好和预算选择合适的模型后端。

### 技术架构一览

从代码结构来看，CodeWiki 采用了前后端分离的架构：

- **前端（fe/）**：提供 Web 界面，用户可以输入仓库地址、配置参数、查看生成的文档。
- **后端（be/）**：核心处理引擎，包含多个关键模块：
  - `dependency_analyzer/`：负责 AST 解析和模块依赖分析，支持多种语言的语法树解析。
  - `cluster_modules.py`：将分析出的模块进行聚类分组，形成有逻辑层次的模块结构。
  - `agent_tools/`：多 Agent 系统的工具集，定义了各个 Agent 可以调用的能力。
  - `llm_services.py`：LLM 服务的统一抽象层，屏蔽不同模型提供商的差异。
  - `documentation_generator.py`：文档生成器，负责将各 Agent 的输出整合为最终文档。
  - `prompt_template.py`：Prompt 模板管理，确保文档生成的一致性和质量。

### 效果如何？与 DeepWiki 的对比

为了评估代码文档的质量，CodeWiki 团队还推出了配套的评测基准 **[CodeWikiBench](https://github.com/FSoft-AI4Code/CodeWikiBench)**，涵盖多种编程语言的仓库级文档质量评估。

根据论文中的实验数据，CodeWiki 在 CodeWikiBench 上的整体平均得分比 DeepWiki 高出约 **4.73%**，尤其在 Python、JavaScript 等脚本语言上表现突出。在 C/C++ 等系统级语言上，由于代码结构更加复杂（宏定义、指针、内存管理等），DeepWiki 在该类别上略占优势（高出约 3.15%），但 CodeWiki 在整体表现上仍然领先。

这个成绩说明 CodeWiki 作为一个开源方案，在文档生成质量上已经可以与商业产品一较高下。

### 快速上手

安装 CodeWiki 非常简单，前置依赖为 Python 3.12+ 和 Node.js（用于 Mermaid 图表验证），然后运行：

```bash
pip install git+https://github.com/FSoft-AI4Code/CodeWiki.git
```

安装完成后，进入目标项目目录，通过 CLI 命令行直接生成文档：

```bash
cd /path/to/your/project
codewiki generate --output docs
```

也可以通过 Web 界面进行交互式操作，支持配置模型后端、选择目标语言、调整文档粒度等参数。此外，CodeWiki 还支持一些实用的高级功能：使用 `--update` 参数可以只重新生成发生变更的模块，大幅提升大型项目的更新效率；通过 `--github-pages --create-branch` 可以一键生成可部署到 GitHub Pages 的 HTML 文档页面；项目还支持 Docker 容器化部署。

### 适用场景

CodeWiki 特别适合以下几种场景：

**新人 Onboarding**。当一个新成员加入团队时，面对一个有几十万行代码的仓库，CodeWiki 可以帮他快速建立对项目的整体认知，了解模块划分和核心逻辑，大幅缩短上手时间。

**开源项目维护**。开源项目的文档质量直接影响社区的参与度。用 CodeWiki 自动生成并更新文档，可以降低维护者的文档负担，让更多人愿意参与贡献。

**代码审查与重构**。在进行大规模重构或代码审查时，CodeWiki 生成的架构文档可以帮助团队更好地理解模块间的依赖关系，避免"牵一发而动全身"的风险。

**技术选型与调研**。当你需要评估一个陌生的开源项目是否适合你的需求时，CodeWiki 可以帮你快速生成一份项目概览，省去大量阅读源码的时间。

### 总结

值得一提的是，CodeWiki 还支持作为 MCP（Model Context Protocol）服务器运行，可以集成到 Claude Desktop、Cursor 等 AI 编程工具中，让 AI 在理解代码时能够直接参考生成的文档，实现更精准的代码问答和辅助开发。

CodeWiki 代表了代码文档自动化领域的一个重要进展。它不是简单的 docstring 提取工具，而是一个能够理解代码架构、生成全景文档的智能系统。作为 ACL 2026 收录的学术工作，它既有扎实的理论基础，又提供了开箱即用的工程实现。对于任何需要理解和维护大型代码仓库的团队来说，CodeWiki 都是一个值得关注和尝试的工具。

---

**项目信息**

- GitHub：[https://github.com/FSoft-AI4Code/CodeWiki](https://github.com/FSoft-AI4Code/CodeWiki)
- 官网：[https://fsoft-ai4code.github.io/CodeWiki/](https://fsoft-ai4code.github.io/CodeWiki/)
- 论文：ACL 2026 收录
- 开发语言：Python（需要 3.12+）
- 支持语言：Python、Java、JavaScript、TypeScript、C、C++、C#、Kotlin
