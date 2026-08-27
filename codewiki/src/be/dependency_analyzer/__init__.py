# Copyright (c) Meta Platforms, Inc. and affiliates
"""
Dependency analyzer module for building and processing import dependency graphs
between Python code components.

Note: ``DependencyParser`` and ``DependencyGraphBuilder`` are lazy-loaded via
PEP 562 ``__getattr__``. They pull in the heavy AST/tree-sitter engine and
should only be imported when actually needed — not when merely importing the
lightweight ``Node`` model, which lives here alongside the graph utilities.
"""

from codewiki.src.be.dependency_analyzer.models.core import Node
from codewiki.src.be.dependency_analyzer.topo_sort import topological_sort, resolve_cycles, build_graph_from_components, dependency_first_dfs, get_leaf_nodes

__all__ = [
    'Node',
    'topological_sort',
    'resolve_cycles',
    'build_graph_from_components',
    'dependency_first_dfs',
    'get_leaf_nodes',
    'DependencyParser',
    'DependencyGraphBuilder',
]

_LAZY_IMPORTS = {
    'DependencyParser': (
        'codewiki.src.be.dependency_analyzer.ast_parser',
        'DependencyParser',
    ),
    'DependencyGraphBuilder': (
        'codewiki.src.be.dependency_analyzer.dependency_graphs_builder',
        'DependencyGraphBuilder',
    ),
}


def __getattr__(name):
    import importlib

    if name in _LAZY_IMPORTS:
        module_path, attr = _LAZY_IMPORTS[name]
        obj = getattr(importlib.import_module(module_path), attr)
        globals()[name] = obj
        return obj
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
