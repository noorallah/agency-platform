"""Report the permission code every HTTP endpoint enforces.

Read from the source tree with :mod:`ast` rather than from a running
application, so it needs no database, no server and no settings file. What it
answers is the question a workflow table has to get right: *who is allowed to
call this, and does the code that guards it match the one the seed grants.*

Two things it deliberately reports rather than hides. A handler whose only
guard is ``require_platform_admin`` prints ``PLATFORM-ADMIN``, because that is
also what an **unseeded** permission code silently degrades to. And a handler
carrying a firm scope with no permission code prints ``firm-scope only`` --
membership of the firm is the whole check, which is right for a directory of
names and wrong for anything that acts on one.

Usage::

    uv run python scripts/dump_route_permissions.py            # every module
    uv run python scripts/dump_route_permissions.py firms      # one module
    uv run python scripts/dump_route_permissions.py --markdown customers
"""

from __future__ import annotations

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "app"

#: Helpers that name the permission codes they enforce, and how to join them.
_CODE_CALLS = {
    "require_permission": " + ",
    "firm_permission_scope": " + ",
    "require_any_permission": " or ",
    "require_feature": " + feature ",
    "require_module": " + module ",
}
_HTTP_METHODS = ("get", "post", "put", "patch", "delete")


@dataclass(frozen=True, slots=True)
class Endpoint:
    """One route, and the guard standing in front of it."""

    method: str
    path: str
    handler: str
    guard: str


def _guard_of(node: ast.AST) -> str | None:
    """Return the guard expressed by an annotation or dependency expression.

    Args:
        node: Any expression that may contain an authorization helper call.

    Returns:
        The permission code, a marker for the guards that name none, or None.

    """
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
            joiner = _CODE_CALLS.get(sub.func.id)
            if joiner is not None:
                codes = [a.value for a in sub.args if isinstance(a, ast.Constant)]
                if codes:
                    return joiner.join(str(code) for code in codes)
            if sub.func.id == "require_platform_admin":
                return "PLATFORM-ADMIN"
            if sub.func.id in ("required_firm_scope", "optional_firm_scope"):
                return "firm-scope only"
            if sub.func.id in ("get_current_principal", "require_authenticated"):
                return "authenticated"
        if isinstance(sub, ast.Name) and sub.id in (
            "RequiredFirmScope",
            "OptionalFirmScope",
        ):
            return "firm-scope only"
        if isinstance(sub, ast.Name) and sub.id in (
            "get_current_principal",
            "require_authenticated",
        ):
            return "authenticated"
    return None


def _aliases(tree: ast.Module) -> dict[str, str]:
    """Collect the module-level ``XxxScope = Annotated[...]`` guard aliases."""
    found: dict[str, str] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and node.targets:
            name = getattr(node.targets[0], "id", None)
        elif isinstance(node, ast.AnnAssign):
            name = getattr(node.target, "id", None)
        else:
            continue
        if name is None or node.value is None:
            continue
        guard = _guard_of(node.value)
        if guard is not None:
            found[name] = guard
    return found


def _dependency_guards(tree: ast.Module) -> dict[str, str]:
    """Collect guards declared by module-level dependency **functions**.

    `app/common/audit` resolves its scope with a plain function whose own
    parameters carry ``require_permission("AUDIT_LOG_VIEW")``. Reading only
    alias assignments reports that endpoint as unguarded, which is the one
    mistake a permission table must not make.
    """
    found: dict[str, str] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        for arg in [*node.args.args, *node.args.kwonlyargs]:
            if arg.annotation is None:
                continue
            guard = _guard_of(arg.annotation)
            if guard is not None and guard != "authenticated":
                found[node.name] = guard
                break
    return found


def _routes(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, str]]:
    """Return the (method, path) pairs a handler is decorated with."""
    routes: list[tuple[str, str]] = []
    for dec in node.decorator_list:
        if (
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Attribute)
            and dec.func.attr in _HTTP_METHODS
        ):
            first = dec.args[0] if dec.args else None
            path = first.value if isinstance(first, ast.Constant) else ""
            routes.append((dec.func.attr.upper(), str(path)))
    return routes


def _guards(
    node: ast.FunctionDef | ast.AsyncFunctionDef, aliases: dict[str, str]
) -> list[str]:
    """Return every guard a handler composes, in the order it declares them."""
    guards: list[str] = []

    def add(value: str | None) -> None:
        if value is not None and value not in guards:
            guards.append(value)

    for arg in [*node.args.args, *node.args.kwonlyargs]:
        if arg.annotation is None:
            continue
        annotation = ast.unparse(arg.annotation)
        for alias, guard in aliases.items():
            if re.search(rf"\b{re.escape(alias)}\b", annotation):
                add(guard)
        add(_guard_of(arg.annotation))
    for dec in node.decorator_list:
        if isinstance(dec, ast.Call):
            for keyword in dec.keywords:
                if keyword.arg == "dependencies":
                    add(_guard_of(keyword.value))
    return guards


def scan(path: Path) -> list[Endpoint]:
    """Return every endpoint declared in one router file."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    aliases = {**_dependency_guards(tree), **_aliases(tree)}
    endpoints: list[Endpoint] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        routes = _routes(node)
        if not routes:
            continue
        guard = ", ".join(_guards(node, aliases)) or "-- none --"
        for method, path_value in routes:
            endpoints.append(Endpoint(method, path_value or "", node.name, guard))
    return endpoints


def routers(modules: list[str]) -> list[Path]:
    """Return the router files for the named modules, or for all of them."""
    roots = [APP / name for name in modules] if modules else [APP]
    files: list[Path] = []
    for root in roots:
        # `app/api/routers/health.py` lives one level below its `api` package,
        # so matching on the parent directory alone misses three endpoints.
        files.extend(
            path
            for path in sorted(root.rglob("*.py"))
            if "api" in path.relative_to(APP).parts and path.name != "__init__.py"
        )
    return files


def render(path: Path, endpoints: list[Endpoint], *, markdown: bool) -> str:
    """Format one router's endpoints as a table."""
    relative = path.relative_to(APP.parent)
    if not markdown:
        lines = [f"### {relative}"]
        lines += [
            f"{e.method:6} {e.path or '(root)':44} {e.guard:38} {e.handler}"
            for e in endpoints
        ]
        return "\n".join(lines)
    lines = [
        f"**`{relative}`**",
        "",
        "| Method | Path | Permission | Handler |",
        "| --- | --- | --- | --- |",
    ]
    lines += [
        f"| {e.method} | `{e.path or '(root)'}` | `{e.guard}` | `{e.handler}` |"
        for e in endpoints
    ]
    return "\n".join(lines)


def main() -> int:
    """Print the endpoint-to-permission table for the requested modules."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("modules", nargs="*", help="Module names; default is all.")
    parser.add_argument("--markdown", action="store_true", help="Emit markdown tables.")
    args = parser.parse_args()
    for path in routers(args.modules):
        endpoints = scan(path)
        if endpoints:
            print(render(path, endpoints, markdown=args.markdown))
            print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
