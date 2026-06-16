# dependency_order.py
"""의존성 위상 정렬 — callee(피호출/피의존)가 caller보다 먼저 오도록 정렬한다."""
from collections import deque
from collections.abc import Iterable


def order_by_dependency(
    nodes: Iterable[str],
    edges: list[tuple[str, str]],
) -> tuple[list[str], list[str]]:
    """
    edges: (caller, callee) — caller가 callee에 의존하므로 callee를 먼저 처리한다.
    반환: (ordered, cycle_nodes)
      - ordered: 의존성 순서 리스트. 순환에 속한 노드는 제외.
      - cycle_nodes: 순환 의존으로 정렬 불가한 노드(사전순).
    노드/엣지에 없는 식별자와 self-loop은 무시한다.
    """
    nodes = set(nodes)
    deps: dict[str, set[str]] = {n: set() for n in nodes}
    dependents: dict[str, set[str]] = {n: set() for n in nodes}
    for caller, callee in edges:
        if caller not in nodes or callee not in nodes or caller == callee:
            continue
        deps[caller].add(callee)
        dependents[callee].add(caller)

    in_degree = {n: len(deps[n]) for n in nodes}
    ready = deque(sorted(n for n in nodes if in_degree[n] == 0))
    ordered: list[str] = []
    while ready:
        n = ready.popleft()
        ordered.append(n)
        for dep in sorted(dependents[n]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                ready.append(dep)

    cycle_nodes = sorted(n for n in nodes if in_degree[n] > 0)
    return ordered, cycle_nodes
