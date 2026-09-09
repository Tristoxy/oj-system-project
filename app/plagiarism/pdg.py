"""Lightweight AST/CFG/PDG construction and approximate graph matching."""

import ast
import copy
import difflib
import io
import keyword
import re
import tokenize
from collections import Counter
from typing import Any


# 函数 `build_pdg`：负责当前模块中的对应操作。
def build_pdg(code: str, language: str) -> dict[str, Any]:
    if language == "python":
        return _build_python_pdg(code)
    return _build_token_pdg(code)


# 函数 `graph_similarity`：负责当前模块中的对应操作。
def graph_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_nodes = Counter(node["label"] for node in left.get("nodes", []))
    right_nodes = Counter(node["label"] for node in right.get("nodes", []))
    node_score = _multiset_jaccard(left_nodes, right_nodes)

    # 函数 `edge_features`：负责当前模块中的对应操作。
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


# 函数 `map_similar_nodes`：负责当前模块中的对应操作。
def map_similar_nodes(
    left: dict[str, Any],
    right: dict[str, Any],
) -> list[dict[str, int]]:
    """Greedily map normalized statements for a compact report summary."""
    right_by_label: dict[str, list[dict[str, Any]]] = {}
    for node in right.get("nodes", []):
        right_by_label.setdefault(str(node.get("label", "")), []).append(node)

    mapping: list[dict[str, int]] = []
    used: set[int] = set()
    for left_node in left.get("nodes", []):
        candidates = right_by_label.get(str(left_node.get("label", "")), [])
        match = next(
            (node for node in candidates if int(node.get("id", -1)) not in used),
            None,
        )
        if match is None:
            continue
        right_id = int(match.get("id", -1))
        used.add(right_id)
        mapping.append(
            {
                "left_node_id": int(left_node.get("id", -1)),
                "right_node_id": right_id,
                "left_line": int(left_node.get("line", 0)),
                "right_line": int(match.get("line", 0)),
            }
        )
    return mapping


# 函数 `_multiset_jaccard`：负责当前模块中的对应操作。
def _multiset_jaccard(left: Counter, right: Counter) -> float:
    union = sum((left | right).values())
    return 1.0 if union == 0 else sum((left & right).values()) / union


# 函数 `_build_python_pdg`：负责当前模块中的对应操作。
def _build_python_pdg(code: str) -> dict[str, Any]:
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return _build_token_pdg(code)

    nodes: list[dict[str, Any]] = []
    flow_edges: set[tuple[int, int]] = set()
    control_edges: set[tuple[int, int]] = set()
    definitions: dict[int, set[str]] = {}
    uses: dict[int, set[str]] = {}

    # 函数 `add_node`：负责当前模块中的对应操作。
    def add_node(statement: ast.stmt) -> int:
        node_id = len(nodes)
        header = _statement_header(statement)
        loads, stores = _names(header)
        if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            stores.add(statement.name)
        nodes.append(
            {
                "id": node_id,
                "label": _normalized_ast_label(header),
                "line": getattr(statement, "lineno", 0),
            }
        )
        definitions[node_id] = stores
        uses[node_id] = loads
        return node_id

    # 函数 `build_block`：负责当前模块中的对应操作。
    def build_block(
        statements: list[ast.stmt],
        incoming: set[int],
        controller: int | None = None,
    ) -> set[int]:
        exits = set(incoming)
        for statement in statements:
            node_id = add_node(statement)
            flow_edges.update((source, node_id) for source in exits)
            if controller is not None:
                control_edges.add((controller, node_id))

            if isinstance(statement, ast.If):
                body_exits = (
                    build_block(statement.body, {node_id}, node_id)
                    if statement.body
                    else {node_id}
                )
                else_exits = (
                    build_block(statement.orelse, {node_id}, node_id)
                    if statement.orelse
                    else {node_id}
                )
                exits = body_exits | else_exits
            elif isinstance(statement, (ast.For, ast.AsyncFor, ast.While)):
                body_exits = (
                    build_block(statement.body, {node_id}, node_id)
                    if statement.body
                    else {node_id}
                )
                flow_edges.update((source, node_id) for source in body_exits)
                exits = {node_id}
                if statement.orelse:
                    exits = build_block(statement.orelse, exits, node_id)
            elif isinstance(statement, (ast.With, ast.AsyncWith)):
                exits = build_block(statement.body, {node_id}, node_id)
            elif isinstance(statement, ast.Try):
                normal_exits = build_block(statement.body, {node_id}, node_id)
                if statement.orelse:
                    normal_exits = build_block(
                        statement.orelse,
                        normal_exits,
                        node_id,
                    )
                branch_exits = set(normal_exits)
                for handler in statement.handlers:
                    branch_exits.update(
                        build_block(handler.body, {node_id}, node_id)
                    )
                exits = (
                    build_block(statement.finalbody, branch_exits, node_id)
                    if statement.finalbody
                    else branch_exits
                )
            elif isinstance(statement, ast.Match):
                case_exits = {node_id}
                for case in statement.cases:
                    case_exits.update(build_block(case.body, {node_id}, node_id))
                exits = case_exits
            elif isinstance(
                statement,
                (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef),
            ):
                # 嵌套作用域属于分析图，但计算定义语句本身时不会执行其中内容。
                build_block(statement.body, {node_id}, node_id)
                exits = {node_id}
            elif isinstance(statement, (ast.Return, ast.Raise)):
                exits = set()
            else:
                exits = {node_id}
        return exits

    build_block(tree.body, set())
    data_edges = _reaching_definition_edges(
        len(nodes),
        flow_edges,
        definitions,
        uses,
    )
    edges = [
        {"from": source, "to": target, "type": edge_type}
        for source, target, edge_type in sorted(
            {(source, target, "flow") for source, target in flow_edges}
            | {(source, target, "control") for source, target in control_edges}
            | {(source, target, "data") for source, target in data_edges}
        )
    ]
    return {"language": "python", "nodes": nodes, "edges": edges}


# 函数 `_reaching_definition_edges`：负责当前模块中的对应操作。
def _reaching_definition_edges(
    node_count: int,
    flow_edges: set[tuple[int, int]],
    definitions: dict[int, set[str]],
    uses: dict[int, set[str]],
) -> set[tuple[int, int]]:
    """Add def-use edges using a fixed-point reaching-definitions analysis."""
    predecessors: dict[int, set[int]] = {node_id: set() for node_id in range(node_count)}
    for source, target in flow_edges:
        predecessors[target].add(source)

    incoming: dict[int, set[tuple[str, int]]] = {
        node_id: set() for node_id in range(node_count)
    }
    outgoing: dict[int, set[tuple[str, int]]] = {
        node_id: set() for node_id in range(node_count)
    }
    changed = True
    while changed:
        changed = False
        for node_id in range(node_count):
            new_incoming = set().union(
                *(outgoing[source] for source in predecessors[node_id])
            ) if predecessors[node_id] else set()
            killed = definitions[node_id]
            new_outgoing = {
                definition
                for definition in new_incoming
                if definition[0] not in killed
            }
            new_outgoing.update((name, node_id) for name in killed)
            if new_incoming != incoming[node_id] or new_outgoing != outgoing[node_id]:
                incoming[node_id] = new_incoming
                outgoing[node_id] = new_outgoing
                changed = True

    return {
        (definition_id, node_id)
        for node_id in range(node_count)
        for name, definition_id in incoming[node_id]
        if name in uses[node_id] and definition_id != node_id
    }


# 函数 `_statement_header`：负责当前模块中的对应操作。
def _statement_header(node: ast.stmt) -> ast.stmt:
    """Return a copy without nested blocks for one statement-level CFG node."""
    header = copy.deepcopy(node)
    for attribute in ("body", "orelse", "finalbody"):
        value = getattr(header, attribute, None)
        if isinstance(value, list):
            setattr(header, attribute, [])
    if isinstance(header, ast.Try):
        header.handlers = []
    if isinstance(header, ast.Match):
        header.cases = []
    return header


# 函数 `_normalized_ast_label`：负责当前模块中的对应操作。
def _normalized_ast_label(node: ast.AST) -> str:
    class Normalizer(ast.NodeTransformer):
        # 函数 `visit_Name`：负责当前模块中的对应操作。
        def visit_Name(self, item: ast.Name):
            return ast.copy_location(ast.Name(id="VAR", ctx=item.ctx), item)

        # 函数 `visit_arg`：负责当前模块中的对应操作。
        def visit_arg(self, item: ast.arg):
            return ast.copy_location(ast.arg(arg="ARG", annotation=None), item)

        # 函数 `visit_Constant`：负责当前模块中的对应操作。
        def visit_Constant(self, item: ast.Constant):
            kind = type(item.value).__name__
            return ast.copy_location(ast.Constant(value=f"<{kind}>"), item)

    normalized = Normalizer().visit(copy.deepcopy(node))
    return ast.dump(normalized, annotate_fields=False, include_attributes=False)


# 函数 `_names`：负责当前模块中的对应操作。
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


# 函数 `_build_token_pdg`：负责当前模块中的对应操作。
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
