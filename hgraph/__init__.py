"""hgraph — a plain-files semantic graph for autoformalization.

Nodes and edges are Markdown/YAML files under ``<project>/hgraph/``; drive them
with the ``hgraph`` CLI (``python -m hgraph ...``) or this API. See ``graph.py``.
"""

from .graph import Edge, Graph, HGraphError, Node

__all__ = ["Graph", "Node", "Edge", "HGraphError"]
