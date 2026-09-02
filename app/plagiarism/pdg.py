"""Lightweight AST/CFG/PDG construction and approximate graph matching."""

import ast
import difflib
import io
import keyword
import re
import tokenize
from collections import Counter
from typing import Any


def build_pdg(code: str, language: str) -> dict[str, Any]:
    if language == "python":
        return _build_python_pdg(code)
    return _build_token_pdg(code)


def graph_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_nodes = Counter(node["label"] for node in left.get("nodes", []))
    right_nodes = Counter(node["label"] for node in right.get("nodes", []))
    node_score = _multiset_jaccard(left_nodes, right_nodes)

    def edge_features(graph):
        labels = {node["id"]: node["label"] for node in graph.get("nodes", [])}
        return Counter(
            (labels.get(edge["from"], ""), edge["type"], labels.get(edge["to"], ""))
            for edge in graph.get("edges", [])
        )

    edge_score = _multiset_jaccard(edge_features(left), edge_features(right))
    left_sequence = [node["label"] for node in left.get("nodes", [])]
    right_sequence = [node["label"] for node in right.get("nodes", [])]
    sequence_score = difflib.SequenceMatcher(None, left_sequence, right_sequence).ratio()
    return round(0.55 * node_score + 0.30 * edge_score + 0.15 * sequence_score, 4)


def _multiset_jaccard(left: Counter, right: Counter) -> float:
    union = sum((left | right).values())
    return 1.0 if union == 0 else sum((left & right).values()) / union


def _build_python_pdg(code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _build_token_pdg(code)

    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    last_definition: dict[str, int] = {}
    previous: int | None = None

    def visit_statements(statements: list[ast.stmt], controller: int | None = None) -> None:
        nonlocal previous
        for statement in statements:
            node_id = len(nodes)
            label = _normalized_ast_label(statement)
            nodes.append({"id": node_id, "label": label, "line": getattr(statement, "lineno", 0)})
            if previous is not None:
                edges.append({"from": previous, "to": node_id, "type": "flow"})
            if controller is not None:
                edges.append({"from": controller, "to": node_id, "type": "control"})
            loads, stores = _names(statement)
            for name in sorted(loads):
                if name in last_definition:
                    edges.append({"from": last_definition[name], "to": node_id, "type": "data"})
            for name in stores:
                last_definition[name] = node_id
            previous = node_id
            nested: list[list[ast.stmt]] = []
            for attribute in ("body", "orelse", "finalbody"):
                value = getattr(statement, attribute, None)
                if isinstance(value, list) and value:
                    nested.append(value)
            handlers = getattr(statement, "handlers", [])
            nested.extend(handler.body for handler in handlers)
            for block in nested:
                visit_statements(block, node_id)

    visit_statements(tree.body)
    return {"language": "python", "nodes": nodes, "edges": edges}


def _normalized_ast_label(node: ast.AST) -> str:
    class Normalizer(ast.NodeTransformer):
        def visit_Name(self, item: ast.Name):
            return ast.copy_location(ast.Name(id="VAR", ctx=item.ctx), item)

        def visit_arg(self, item: ast.arg):
            return ast.copy_location(ast.arg(arg="ARG", annotation=None), item)

        def visit_Constant(self, item: ast.Constant):
            kind = type(item.value).__name__
            return ast.copy_location(ast.Constant(value=f"<{kind}>"), item)

    normalized = Normalizer().visit(ast.fix_missing_locations(ast.parse(ast.unparse(node)))).body[0]
    return ast.dump(normalized, annotate_fields=False, include_attributes=False)


def _names(node: ast.AST) -> tuple[set[str], set[str]]:
    loads: set[str] = set()
    stores: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name):
            if isinstance(child.ctx, ast.Load):
                loads.add(child.id)
            elif isinstance(child.ctx, (ast.Store, ast.Del)):
                stores.add(child.id)
    return loads, stores


def _build_token_pdg(code: str) -> dict[str, Any]:
    normalized: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(code).readline)
        for token in tokens:
            if token.type == tokenize.NAME and not keyword.iskeyword(token.string):
                normalized.append("VAR")
            elif token.type == tokenize.NUMBER:
                normalized.append("NUMBER")
            elif token.type == tokenize.STRING:
                normalized.append("STRING")
            elif token.type not in {
                tokenize.ENCODING,
                tokenize.ENDMARKER,
                tokenize.INDENT,
                tokenize.DEDENT,
                tokenize.NL,
                tokenize.NEWLINE,
            }:
                normalized.append(token.string)
    except (tokenize.TokenError, IndentationError):
        normalized = re.findall(r"[A-Za-z_]+|\d+|[^\s]", code)
    chunks = [" ".join(normalized[index : index + 12]) for index in range(0, len(normalized), 12)]
    nodes = [{"id": index, "label": chunk, "line": 0} for index, chunk in enumerate(chunks)]
    edges = [
        {"from": index - 1, "to": index, "type": "flow"}
        for index in range(1, len(nodes))
    ]
    return {"language": "tokens", "nodes": nodes, "edges": edges}
