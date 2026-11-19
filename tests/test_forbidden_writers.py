"""AST scan enforcing architectural invariant: no code outside inventory.services mutates stock."""

import ast
from pathlib import Path

APPS_DIR = Path(__file__).resolve().parent.parent / "apps"
ALLOWED_WRITER_FILES = {
    APPS_DIR / "inventory" / "services.py",
}


class StockLevelMutationVisitor(ast.NodeVisitor):
    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.violations: list[str] = []

    def visit_Assign(self, node: ast.Assign) -> None:
        """Catch direct attribute assignments like `obj.on_hand = ...`."""
        for target in node.targets:
            if isinstance(target, ast.Attribute) and target.attr in {"on_hand", "reserved"}:
                msg = f"{self.file_path}:{node.lineno} - Direct write to '{target.attr}' forbidden."
                self.violations.append(msg)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        """Catch QuerySet `.update(on_hand=...)` or `.update(reserved=...)` calls."""
        if isinstance(node.func, ast.Attribute) and node.func.attr == "update":
            for kw in node.keywords:
                if kw.arg in {"on_hand", "reserved"}:
                    msg = (
                        f"{self.file_path}:{node.lineno} - QuerySet.update({kw.arg}=...) forbidden."
                    )
                    self.violations.append(msg)
        self.generic_visit(node)


def test_no_forbidden_stock_writers_outside_inventory_services():
    """Verify via AST parsing that NO file outside apps/inventory/services.py modifies stock."""
    all_violations: list[str] = []

    for py_file in APPS_DIR.rglob("*.py"):
        # Ignore migrations and compiled files
        if "migrations" in py_file.parts or "__pycache__" in py_file.parts:
            continue
        # Skip allowed service files
        if py_file.resolve() in ALLOWED_WRITER_FILES:
            continue

        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))
            visitor = StockLevelMutationVisitor(py_file)
            visitor.visit(tree)
            all_violations.extend(visitor.violations)
        except Exception as e:
            all_violations.append(f"Failed to parse {py_file}: {e}")

    assert not all_violations, (
        "Architectural violation: direct mutations to StockLevel.on_hand or StockLevel.reserved "
        "were found outside apps/inventory/services.py:\n" + "\n".join(all_violations)
    )
