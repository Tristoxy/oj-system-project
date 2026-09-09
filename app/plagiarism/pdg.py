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


# Python 代码优先构建 AST/CFG/PDG；其他语言或语法错误则降级为 Token 流图。
def build_pdg(code: str, language: str) -> dict[str, Any]:
    if language == "python":
        return _build_python_pdg(code)
    return _build_token_pdg(code)


# 综合节点多重集、带类型边和语句顺序三项相似度，输出 0–1 的加权分数。
def graph_similarity(left: dict[str, Any], right: dict[str, Any]) -> float:
    left_nodes = Counter(node["label"] for node in left.get("nodes", []))
    right_nodes = Counter(node["label"] for node in right.get("nodes", []))
    node_score = _multiset_jaccard(left_nodes, right_nodes)

    # 将每条边转换为“源标签、边类型、目标标签”，使节点编号变化不影响比较。
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


# 按规范化标签贪心匹配未使用节点，生成报告可展示的节点与源代码行号对应关系。
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


# 用 Counter 的交并集计算保留重复次数的 Jaccard 相似度。
def _multiset_jaccard(left: Counter, right: Counter) -> float:
    union = sum((left | right).values())
    return 1.0 if union == 0 else sum((left & right).values()) / union


# 从 Python AST 构造语句节点、顺序流边、控制依赖边和定义—使用数据边。
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

    # 为一条语句创建规范化节点，同时记录该语句读取和定义的变量集合。
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

    # 递归展开代码块，连接分支、循环、异常和嵌套作用域的流边与控制边。
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


# 用到达定义不动点分析找出每次变量读取可能对应的定义节点，并建立数据边。
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


# 深拷贝语句并移除嵌套块，只保留当前 CFG 节点自身的语法头部。
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


# 将变量名、参数名和常量值匿名化后序列化 AST，使简单改名不能规避查重。
def _normalized_ast_label(node: ast.AST) -> str:
    class Normalizer(ast.NodeTransformer):
        # 把所有变量引用统一替换为 VAR，同时保留 Load/Store 上下文。
        def visit_Name(self, item: ast.Name):
            return ast.copy_location(ast.Name(id="VAR", ctx=item.ctx), item)

        # 把函数形参名统一替换为 ARG，并移除可能泄露原结构的类型标注。
        def visit_arg(self, item: ast.arg):
            return ast.copy_location(ast.arg(arg="ARG", annotation=None), item)

        # 只保留常量的数据类型，不保留具体字符串或数值。
        def visit_Constant(self, item: ast.Constant):
            kind = type(item.value).__name__
            return ast.copy_location(ast.Constant(value=f"<{kind}>"), item)

    normalized = Normalizer().visit(copy.deepcopy(node))
    return ast.dump(normalized, annotate_fields=False, include_attributes=False)


# 遍历语句头 AST，分别收集被读取和被定义/删除的变量名。
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


# 将标识符和字面量归一化后按固定窗口建顺序图，作为非 Python 代码的查重表示。
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
