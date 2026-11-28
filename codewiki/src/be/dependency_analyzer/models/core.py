from pydantic import BaseModel
from typing import Any, Dict, List, Optional, Set


class Node(BaseModel):
    id: str

    name: str

    component_type: str

    file_path: str

    relative_path: str

    depends_on: Set[str] = set()

    # 语言分析器可持久化的原始引用语义；Dart 用它复核增量边，
    # 避免 receiver 类型或可见域变化后仅凭目标名复活旧边。
    metadata: Dict[str, Any] = {}

    source_code: Optional[str] = None

    start_line: int = 0

    end_line: int = 0

    has_docstring: bool = False

    docstring: str = ""

    parameters: Optional[List[str]] = None

    node_type: Optional[str] = None

    base_classes: Optional[List[str]] = None

    class_name: Optional[str] = None

    display_name: Optional[str] = None

    component_id: Optional[str] = None

    language: Optional[str] = None

    qualified_name: Optional[str] = None

    def get_display_name(self) -> str:
        return self.display_name or self.name


class CallRelationship(BaseModel):
    caller: str

    callee: str

    call_line: Optional[int] = None

    is_resolved: bool = False


class Repository(BaseModel):
    url: str

    name: str

    clone_path: str

    analysis_id: str
