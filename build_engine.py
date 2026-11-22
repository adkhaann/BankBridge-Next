"""
Builds engine.py from app.py.

app.py stays your "source of truth" (you can keep adding banks to it exactly
as before). This script copies only the reusable parts - imports, functions,
classes and ALL_CAPS settings such as SUPPORTED_COMBINATIONS - into engine.py,
and leaves out the old Streamlit screen code. The new BankBridge screen
(bankbridge_ui.py) then imports engine.py.
"""
import ast
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SOURCE = os.path.join(HERE, "app.py")
TARGET = os.path.join(HERE, "engine.py")


def is_constant_assignment(node):
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, ast.AnnAssign):
        targets = [node.target]
    else:
        return False
    return all(
        isinstance(t, ast.Name) and t.id.isupper() for t in targets
    )


def build(source=SOURCE, target=TARGET):
    with open(source, encoding="utf-8-sig") as f:
        text = f.read()

    tree = ast.parse(text, filename=source)
    lines = text.splitlines()
    kept = []

    for node in tree.body:
        keep = isinstance(
            node,
            (ast.Import, ast.ImportFrom, ast.FunctionDef,
             ast.AsyncFunctionDef, ast.ClassDef)
        ) or is_constant_assignment(node)
        if not keep:
            continue
        start = node.lineno
        if getattr(node, "decorator_list", None):
            start = min(d.lineno for d in node.decorator_list)
        kept.append("\n".join(lines[start - 1:node.end_lineno]))

    header = (
        "# AUTO-GENERATED from app.py by build_engine.py - do not edit.\n"
        "# Edit app.py instead; this file is rebuilt automatically.\n\n"
    )
    output = header + "\n\n\n".join(kept) + "\n"
    compile(output, target, "exec")  # fail early if something is wrong

    with open(target, "w", encoding="utf-8") as f:
        f.write(output)
    return target


def needs_rebuild(source=SOURCE, target=TARGET):
    if not os.path.exists(target):
        return True
    return os.path.getmtime(source) > os.path.getmtime(target)


if __name__ == "__main__":
    if not os.path.exists(SOURCE):
        print("ERROR: app.py not found next to build_engine.py")
        sys.exit(1)
    build()
    print("engine.py built from app.py")
