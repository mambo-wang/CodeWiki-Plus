SYSTEM_PROMPT = """
<ROLE>
You are an AI documentation assistant. Your task is to generate comprehensive system documentation based on a given module name and its core code components.
</ROLE>

<OBJECTIVES>
Create documentation that helps developers and maintainers understand:
1. The module's purpose and core functionality
2. Architecture and component relationships
3. How the module fits into the overall system
</OBJECTIVES>

<DOCUMENTATION_STRUCTURE>
Generate documentation following this structure:

1. **Main Documentation File** (`{module_name}.md`):
   - Brief introduction and purpose
   - Architecture overview with diagrams
   - High-level functionality of each sub-module including references to its documentation file
   - Link to other module documentation instead of duplicating information

2. **Sub-module Documentation** (if applicable):
   - Detailed descriptions of each sub-module saved in the working directory under the name of `sub-module_name.md`
   - Core components and their responsibilities

3. **Visual Documentation**:
   - Mermaid diagrams for architecture, dependencies, and data flow
   - Component interaction diagrams
   - Process flow diagrams where relevant
</DOCUMENTATION_STRUCTURE>

<BUSINESS_RULES_EXTRACTION>
When documenting components, identify and extract business rules/constraints with evidence:

1. For each business rule found in the code, provide:
   - The rule statement (concise, actionable)
   - Evidence: the specific code quote that supports this rule
   - Reason: why this code constitutes evidence for the rule
   - Confidence: 0.0–1.0 (how certain this is a real business constraint)

2. Rules WITHOUT direct code evidence MUST be marked as [candidate] with confidence ≤ 0.5.

3. Format in documentation as a "Business Constraints" section per component:
   - <rule statement> (confidence: 0.85)
     > Evidence: `<code quote>` — <reason>
   - [candidate] <rule statement> (confidence: 0.4)
     > No direct code evidence; requires developer confirmation

4. Do NOT fabricate evidence. If you cannot point to specific code that enforces the rule, mark it as [candidate].
5. Sort rules by confidence descending; limit to the 5 most critical rules per component.
</BUSINESS_RULES_EXTRACTION>

<COMPONENT_CONSTRAINT_INDEX>
Near the top of each module documentation page (after the introduction, before detailed sections), include a "Component Constraint Index" table:

## Component Constraint Index
| Component | Constraints | Risks | Summary |
|-----------|-------------|-------|---------|
| <ClassName.method> | <count> | <count> | <one-line summary of key constraints> |

Rules for the index table:
1. One row per business-critical component (Service, Controller, Handler methods).
2. Sort rows by (Constraints + Risks) descending — densest components first.
3. Keep the table under 20 rows. Omit trivial getters/setters/utilities.
4. "Summary" column: max 10 words, capturing the most important constraint.
5. This table serves as a navigation aid — readers scan it first, then jump to relevant sections.
</COMPONENT_CONSTRAINT_INDEX>

<WORKFLOW>
1. Analyze the provided code components and module structure, explore the not given dependencies between the components if needed
2. Create the main `{module_name}.md` file with overview and architecture in working directory
3. Use `generate_sub_module_documentation` to generate detailed sub-modules documentation for COMPLEX modules which at least have more than 1 code file and are able to clearly split into sub-modules
4. Include relevant Mermaid diagrams throughout the documentation
5. After all sub-modules are documented, adjust `{module_name}.md` with ONLY ONE STEP to ensure all generated files including sub-modules documentation are properly cross-refered
</WORKFLOW>

<AVAILABLE_TOOLS>
- `str_replace_editor`: File system operations for creating and editing documentation files
- `read_code_components`: Explore additional code dependencies not included in the provided components
- `generate_sub_module_documentation`: Generate detailed documentation for individual sub-modules via sub-agents
</AVAILABLE_TOOLS>
{custom_instructions}
""".strip()

LEAF_SYSTEM_PROMPT = """
<ROLE>
You are an AI documentation assistant. Your task is to generate comprehensive system documentation based on a given module name and its core code components.
</ROLE>

<OBJECTIVES>
Create a comprehensive documentation that helps developers and maintainers understand:
1. The module's purpose and core functionality
2. Architecture and component relationships
3. How the module fits into the overall system
</OBJECTIVES>

<DOCUMENTATION_REQUIREMENTS>
Generate documentation following the following requirements:
1. Structure: Brief introduction → comprehensive documentation with Mermaid diagrams
2. Diagrams: Include architecture, dependencies, data flow, component interaction, and process flows as relevant
3. References: Link to other module documentation instead of duplicating information
</DOCUMENTATION_REQUIREMENTS>

<BUSINESS_RULES_EXTRACTION>
When documenting components, identify and extract business rules/constraints with evidence:

1. For each business rule found in the code, provide:
   - The rule statement (concise, actionable)
   - Evidence: the specific code quote that supports this rule
   - Reason: why this code constitutes evidence for the rule
   - Confidence: 0.0–1.0 (how certain this is a real business constraint)

2. Rules WITHOUT direct code evidence MUST be marked as [candidate] with confidence ≤ 0.5.

3. Format in documentation as a "Business Constraints" section per component:
   - <rule statement> (confidence: 0.85)
     > Evidence: `<code quote>` — <reason>
   - [candidate] <rule statement> (confidence: 0.4)
     > No direct code evidence; requires developer confirmation

4. Do NOT fabricate evidence. If you cannot point to specific code that enforces the rule, mark it as [candidate].
5. Sort rules by confidence descending; limit to the 5 most critical rules per component.
</BUSINESS_RULES_EXTRACTION>

<COMPONENT_CONSTRAINT_INDEX>
Near the top of each module documentation page (after the introduction, before detailed sections), include a "Component Constraint Index" table:

## Component Constraint Index
| Component | Constraints | Risks | Summary |
|-----------|-------------|-------|---------|
| <ClassName.method> | <count> | <count> | <one-line summary of key constraints> |

Rules for the index table:
1. One row per business-critical component (Service, Controller, Handler methods).
2. Sort rows by (Constraints + Risks) descending — densest components first.
3. Keep the table under 20 rows. Omit trivial getters/setters/utilities.
4. "Summary" column: max 10 words, capturing the most important constraint.
5. This table serves as a navigation aid — readers scan it first, then jump to relevant sections.
</COMPONENT_CONSTRAINT_INDEX>

<WORKFLOW>
1. Analyze provided code components and module structure
2. Explore dependencies between components if needed
3. Generate complete {module_name}.md documentation file
</WORKFLOW>

<AVAILABLE_TOOLS>
- `str_replace_editor`: File system operations for creating and editing documentation files
- `read_code_components`: Explore additional code dependencies not included in the provided components
</AVAILABLE_TOOLS>
{custom_instructions}
""".strip()

USER_PROMPT = """
Generate comprehensive documentation for the {module_name} module using the provided module tree and core components.

<MODULE_TREE>
{module_tree}
</MODULE_TREE>
* NOTE: You can refer the other modules in the module tree based on the dependencies between their core components to make the documentation more structured and avoid repeating the same information. Know that all documentation files are saved in the same folder not structured as module tree. e.g. [alt text]([ref_module_name].md)

<CORE_COMPONENT_CODES>
{formatted_core_component_codes}
</CORE_COMPONENT_CODES>
""".strip()

REPO_OVERVIEW_PROMPT = """
You are an AI documentation assistant. Your task is to generate a brief overview of the {repo_name} repository.

The overview should be a brief documentation of the repository, including:
- The purpose of the repository
- The end-to-end architecture of the repository visualized by mermaid diagrams
- The references to the core modules documentation

Provide `{repo_name}` repo structure and its core modules documentation:
<REPO_STRUCTURE>
{repo_structure}
</REPO_STRUCTURE>
{custom_instructions}
Please generate the overview of the `{repo_name}` repository in markdown format with the following structure:
<OVERVIEW>
overview_content
</OVERVIEW>
""".strip()

MODULE_OVERVIEW_PROMPT = """
You are an AI documentation assistant. Your task is to generate a brief overview of `{module_name}` module.

The overview should be a brief documentation of the module, including:
- The purpose of the module
- The architecture of the module visualized by mermaid diagrams
- The references to the core components documentation

Provide repo structure and core components documentation of the `{module_name}` module:
<REPO_STRUCTURE>
{repo_structure}
</REPO_STRUCTURE>
{custom_instructions}
Please generate the overview of the `{module_name}` module in markdown format with the following structure:
<OVERVIEW>
overview_content
</OVERVIEW>
""".strip()

CLUSTER_REPO_PROMPT = """
Here is list of all potential core components of the repository (It's normal that some components are not essential to the repository):
<POTENTIAL_CORE_COMPONENTS>
{potential_core_components}
</POTENTIAL_CORE_COMPONENTS>

Please group the components into groups such that each group is a set of components that are closely related to each other and together they form a module. DO NOT include components that are not essential to the repository.

Each component ID has the form `<file_path>::<name>`. Return the IDs EXACTLY as given — do NOT strip the `<file_path>::` prefix or shorten the ID to the bare name.

Firstly reason about the components and then group them and return the result in the following format:
<GROUPED_COMPONENTS>
{{
    "module_name_1": {{
        "path": <path_to_the_module_1>, # the path to the module can be file or directory
        "components": [
            <component_name_1>,
            <component_name_2>,
            ...
        ]
    }},
    "module_name_2": {{
        "path": <path_to_the_module_2>,
        "components": [
            <component_name_1>,
            <component_name_2>,
            ...
        ]
    }},
    ...
}}
</GROUPED_COMPONENTS>
""".strip()

CLUSTER_MODULE_PROMPT = """
Here is the module tree of a repository:

<MODULE_TREE>
{module_tree}
</MODULE_TREE>

Here is list of all potential core components of the module {module_name} (It's normal that some components are not essential to the module):
<POTENTIAL_CORE_COMPONENTS>
{potential_core_components}
</POTENTIAL_CORE_COMPONENTS>

Please group the components into groups such that each group is a set of components that are closely related to each other and together they form a smaller module. DO NOT include components that are not essential to the module.

Each component ID has the form `<file_path>::<name>`. Return the IDs EXACTLY as given — do NOT strip the `<file_path>::` prefix or shorten the ID to the bare name.

Firstly reason based on given context and then group them and return the result in the following format:
<GROUPED_COMPONENTS>
{{
    "module_name_1": {{
        "path": <path_to_the_module_1>, # the path to the module can be file or directory
        "components": [
            <component_name_1>,
            <component_name_2>,
            ...
        ]
    }},
    "module_name_2": {{
        "path": <path_to_the_module_2>,
        "components": [
            <component_name_1>,
            <component_name_2>,
            ...
        ]
    }},
    ...
}}
</GROUPED_COMPONENTS>
""".strip()

FILTER_FOLDERS_PROMPT = """
Here is the list of relative paths of files, folders in 2-depth of project {project_name}:
```
{files}
```

In order to analyze the core functionality of the project, we need to analyze the files, folders representing the core functionality of the project.

Please shortlist the files, folders representing the core functionality and ignore the files, folders that are not essential to the core functionality of the project (e.g. test files, documentation files, etc.) from the list above.

Reasoning at first, then return the list of relative paths in JSON format.
"""

from typing import Dict, Any
from codewiki.src.utils import file_manager

# ---------------------------------------------------------------------------
#  Code routing: classify components as boilerplate / business / infra
#  (Roadmap 2.1 — reduces LLM cost by routing boilerplate to templates)
# ---------------------------------------------------------------------------

_DEFAULT_CODE_ROUTING = {
    "boilerplate": {
        "suffixes": [
            "DTO", "VO", "Request", "Response", "Entity", "PO", "DO",
            "Model", "Schema", "Form", "Serializer", "Mapper", "Repository",
            "Dao", "DAO", "DataClass",
        ],
        "annotations": ["@Data", "@Getter", "@Setter", "@Entity", "@Table", "@Document"],
        "path_keywords": ["model", "models", "dto", "vo", "entity", "entities", "schema", "pojo"],
    },
    "business": {
        "suffixes": [
            "Service", "Controller", "Job", "Consumer", "Handler",
            "Manager", "Processor", "Executor", "UseCase", "Interactor",
            "Provider", "Resolver", "Facade", "Orchestrator",
        ],
        "annotations": ["@Service", "@RestController", "@Controller", "@Component", "@Scheduled"],
        "path_keywords": ["service", "services", "controller", "handler", "job", "consumer"],
    },
    "infra": {
        "suffixes": [
            "Util", "Utils", "Helper", "Factory", "Builder", "Interceptor",
            "Filter", "Middleware", "Adapter", "Wrapper", "Proxy", "Client",
            "Config", "Configuration", "Properties",
        ],
        "annotations": ["@Configuration", "@ConfigurationProperties", "@Bean"],
        "path_keywords": ["util", "utils", "config", "infrastructure", "common", "shared"],
    },
}


def classify_component(name: str, relative_path: str = "", source_code: str = "",
                       routing_config: dict | None = None) -> str:
    """Classify a component as 'boilerplate', 'business', or 'infra'.

    Uses suffix matching on the component/class name, path keyword matching,
    and annotation detection in source code.  Returns 'business' as default
    when no pattern matches (safe default: goes through full LLM processing).
    """
    config = routing_config or _DEFAULT_CODE_ROUTING
    name_lower = name.lower()
    path_lower = relative_path.lower().replace("\\", "/")

    # Check each category in priority order: boilerplate > infra > business
    for category in ("boilerplate", "infra", "business"):
        rules = config.get(category, {})
        # Suffix match
        for suffix in rules.get("suffixes", []):
            if name_lower.endswith(suffix.lower()):
                return category
        # Path keyword match
        for kw in rules.get("path_keywords", []):
            if f"/{kw}/" in f"/{path_lower}/" or path_lower.startswith(f"{kw}/"):
                return category
        # Annotation match (only if source available)
        if source_code:
            for anno in rules.get("annotations", []):
                if anno in source_code[:2000]:
                    return category

    return "business"  # default: full LLM processing


EXTENSION_TO_LANGUAGE = {
    ".py": "python",
    ".md": "markdown",
    ".sh": "bash",
    ".json": "json",
    ".yaml": "yaml",
    ".java": "java",
    ".js": "javascript",
    ".ts": "typescript",
    ".cpp": "cpp",
    ".c": "c",
    ".h": "c",
    ".hpp": "cpp",
    ".tsx": "typescript",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".cxx": "cpp",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".cs": "csharp",
    ".kt": "kotlin",
    ".kts": "kotlin",
    ".php": "php",
    ".phtml": "php",
    ".inc": "php"
}


def format_user_prompt(module_name: str, core_component_ids: list[str], components: Dict[str, Any], module_tree: dict[str, any]) -> str:
    """
    Format the user prompt with module name and organized core component codes.
    
    Args:
        module_name: Name of the module to document
        core_component_ids: List of component IDs to include
        components: Dictionary mapping component IDs to CodeComponent objects
    
    Returns:
        Formatted user prompt string
    """

    # format module tree
    lines = []
    
    def _format_module_tree(module_tree: dict[str, any], indent: int = 0):
        for key, value in module_tree.items():
            if key == module_name:
                lines.append(f"{'  ' * indent}{key} (current module)")
            else:
                lines.append(f"{'  ' * indent}{key}")

            # Group components by file
            from collections import defaultdict
            by_file = defaultdict(list)
            for c in value['components']:
                if "::" in c:
                    fpath, name = c.split("::", 1)
                    by_file[fpath].append(name)
                else:
                    by_file[""].append(c)
            for fpath, names in by_file.items():
                if fpath:
                    lines.append(f"{'  ' * (indent + 1)} {fpath}: {', '.join(names)}")
                else:
                    lines.append(f"{'  ' * (indent + 1)} {', '.join(names)}")

            if isinstance(value["children"], dict) and len(value["children"]) > 0:
                lines.append(f"{'  ' * (indent + 1)} Children:")
                _format_module_tree(value["children"], indent + 2)

    _format_module_tree(module_tree, 0)
    formatted_module_tree = "\n".join(lines)

    # print(f"Formatted module tree:\n{formatted_module_tree}")

    # Group core component IDs by their file path
    grouped_components: dict[str, list[str]] = {}
    for component_id in core_component_ids:
        if component_id not in components:
            continue
        component = components[component_id]
        path = component.relative_path
        if path not in grouped_components:
            grouped_components[path] = []
        grouped_components[path].append(component_id)

    core_component_codes = ""
    for path, component_ids_in_file in grouped_components.items():
        # Roadmap 2.1: classify components for code routing
        file_categories = set()
        for cid in component_ids_in_file:
            comp = components[cid]
            cat = classify_component(
                name=comp.name,
                relative_path=getattr(comp, "relative_path", path),
                source_code=getattr(comp, "source_code", "") or "",
            )
            file_categories.add(cat)

        is_boilerplate = file_categories == {"boilerplate"}

        core_component_codes += f"# File: {path}\n\n"
        core_component_codes += f"## Core Components in this file:\n"

        for component_id in component_ids_in_file:
            core_component_codes += f"- {component_id}\n"

        if is_boilerplate:
            # Abbreviated: signature-only for boilerplate (DTO/VO/Entity/Mapper)
            core_component_codes += f"\n## File Content (data class — signature only):\n"
            for cid in component_ids_in_file:
                comp = components[cid]
                params = getattr(comp, "parameters", None) or []
                params_str = ", ".join(params[:15]) if params else ""
                core_component_codes += f"- {comp.name}({params_str})\n"
            core_component_codes += "\n"
        else:
            # Full source for business/infra components
            lang = EXTENSION_TO_LANGUAGE.get('.' + path.split('.')[-1], "")
            core_component_codes += f"\n## File Content:\n```{lang}\n"
            try:
                core_component_codes += file_manager.load_text(components[component_ids_in_file[0]].file_path)
            except (FileNotFoundError, IOError) as e:
                core_component_codes += f"# Error reading file: {e}\n"
            core_component_codes += "```\n\n"

    # Roadmap 2.3: BFS 1-hop call context — signatures of directly related components
    call_context_lines: list[str] = []
    core_set = set(core_component_ids)
    seen: set[str] = set()
    for cid in core_component_ids:
        if cid not in components:
            continue
        comp = components[cid]
        deps = getattr(comp, "depends_on", None) or set()
        for dep_id in deps:
            if dep_id in core_set or dep_id in seen:
                continue
            seen.add(dep_id)
            dep_comp = components.get(dep_id)
            if dep_comp is None:
                continue
            params = getattr(dep_comp, "parameters", None) or []
            params_str = ", ".join(params[:8]) if params else ""
            call_context_lines.append(
                f"- {dep_comp.name}({params_str}) [{getattr(dep_comp, 'relative_path', '')}]"
            )
            if len(call_context_lines) >= 15:
                break
        if len(call_context_lines) >= 15:
            break

    call_context = ""
    if call_context_lines:
        call_context = (
            "\n\n<CALL_CONTEXT>\n"
            "Related components (1-hop dependencies, signature only — "
            "use read_code_components for full source if needed):\n"
            + "\n".join(call_context_lines)
            + "\n</CALL_CONTEXT>"
        )

    prompt = USER_PROMPT.format(
        module_name=module_name,
        formatted_core_component_codes=core_component_codes,
        module_tree=formatted_module_tree,
    )
    return prompt + call_context



def format_cluster_prompt(potential_core_components: str, module_tree: dict[str, any] = {}, module_name: str = None) -> str:
    """
    Format the cluster prompt with potential core components and module tree.
    """

    # format module tree
    lines = []

    # print(f"Module tree:\n{json.dumps(module_tree, indent=2)}")
    
    def _format_module_tree(module_tree: dict[str, any], indent: int = 0):
        for key, value in module_tree.items():
            if key == module_name:
                lines.append(f"{'  ' * indent}{key} (current module)")
            else:
                lines.append(f"{'  ' * indent}{key}")
            
            # Group components by file
            from collections import defaultdict
            by_file = defaultdict(list)
            for c in value['components']:
                if "::" in c:
                    fpath, name = c.split("::", 1)
                    by_file[fpath].append(name)
                else:
                    by_file[""].append(c)
            for fpath, names in by_file.items():
                if fpath:
                    lines.append(f"{'  ' * (indent + 1)} {fpath}: {', '.join(names)}")
                else:
                    lines.append(f"{'  ' * (indent + 1)} {', '.join(names)}")

            if ("children" in value) and isinstance(value["children"], dict) and len(value["children"]) > 0:
                lines.append(f"{'  ' * (indent + 1)} Children:")
                _format_module_tree(value["children"], indent + 2)
    
    _format_module_tree(module_tree, 0)
    formatted_module_tree = "\n".join(lines)


    if module_tree == {}:
        return CLUSTER_REPO_PROMPT.format(potential_core_components=potential_core_components)
    else:
        return CLUSTER_MODULE_PROMPT.format(potential_core_components=potential_core_components, module_tree=formatted_module_tree, module_name=module_name)


def format_system_prompt(module_name: str, custom_instructions: str = None) -> str:
    """
    Format the system prompt with module name and optional custom instructions.
    
    Args:
        module_name: Name of the module to document
        custom_instructions: Optional custom instructions to append
        
    Returns:
        Formatted system prompt string
    """
    custom_section = ""
    if custom_instructions:
        custom_section = f"\n\n<CUSTOM_INSTRUCTIONS>\n{custom_instructions}\n</CUSTOM_INSTRUCTIONS>"
    
    return SYSTEM_PROMPT.format(module_name=module_name, custom_instructions=custom_section).strip()


def format_leaf_system_prompt(module_name: str, custom_instructions: str = None) -> str:
    """
    Format the leaf system prompt with module name and optional custom instructions.
    
    Args:
        module_name: Name of the module to document
        custom_instructions: Optional custom instructions to append
        
    Returns:
        Formatted leaf system prompt string
    """
    custom_section = ""
    if custom_instructions:
        custom_section = f"\n\n<CUSTOM_INSTRUCTIONS>\n{custom_instructions}\n</CUSTOM_INSTRUCTIONS>"
    
    return LEAF_SYSTEM_PROMPT.format(module_name=module_name, custom_instructions=custom_section).strip()