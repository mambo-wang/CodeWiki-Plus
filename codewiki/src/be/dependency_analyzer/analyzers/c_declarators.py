"""Tree-sitter C/C++ 共用的声明符提取辅助函数。"""

from typing import Optional

WRAPPERS = (
    "pointer_declarator",
    "reference_declarator",
    "parenthesized_declarator",
    "attributed_declarator",
)


def _inner(node):
    named = node.child_by_field_name("declarator")
    if named is not None:
        return named
    return next(
        (
            child
            for child in node.named_children
            if child.type.endswith("declarator") or child.type in ("identifier", "field_identifier")
        ),
        None,
    )


def function_declarator(definition):
    found = None
    node = definition.child_by_field_name("declarator")
    while node is not None:
        if node.type == "function_declarator":
            found = node
        elif node.type not in WRAPPERS:
            break
        node = _inner(node)
    return found


def macro_typed_name(declarator) -> Optional[str]:
    name = declarator.child_by_field_name("declarator")
    params = declarator.child_by_field_name("parameters")
    if name is None or name.type != "identifier":
        return None
    errors = [
        child
        for child in declarator.children
        if child.type == "ERROR"
        and child.start_byte >= name.end_byte
        and (params is None or child.end_byte <= params.start_byte)
    ]
    if len(errors) != 1 or [
        child.type for child in errors[0].named_children
    ] != ["identifier"]:
        return None
    text: str = errors[0].named_children[0].text.decode()
    return text


def declarator_name(declarator) -> Optional[str]:
    if name := macro_typed_name(declarator):
        return name
    node = _inner(declarator)
    while node is not None:
        if node.type in ("identifier", "field_identifier"):
            text: str = node.text.decode()
            return text
        if node.type == "qualified_identifier":
            identifiers = [
                child
                for child in node.children
                if child.type in ("identifier", "field_identifier")
            ]
            if identifiers:
                text = identifiers[-1].text.decode()
                return text
        if node.type not in WRAPPERS:
            return None
        node = _inner(node)
    return None


def split_macro_function_name(definition) -> Optional[str]:
    declarator = definition.child_by_field_name("declarator")
    kind = definition.child_by_field_name("type")
    before = definition.prev_named_sibling
    if (
        declarator is None
        or declarator.type != "parenthesized_declarator"
        or [child.type for child in declarator.named_children] != ["identifier"]
        or kind is None
        or kind.type != "type_identifier"
        or before is None
        or before.type != "declaration"
        or not (before.children and before.children[-1].is_missing)
        or before.end_point[0] != definition.start_point[0]
    ):
        return None
    text: str = kind.text.decode()
    return text
