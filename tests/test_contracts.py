"""Keep contracts/ in sync with the API the app actually serves.

Every endpoint under API_PREFIX must have a contract in contracts/openapi.yaml,
every documented endpoint must still exist, and every $ref must resolve.
"""

from pathlib import Path

import yaml

from app.core.config import API_PREFIX
from app.main import app

CONTRACTS_DIR = Path(__file__).resolve().parents[1] / "contracts"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _resolve(ref: str, base: Path) -> tuple[object, Path]:
    file_part, _, pointer = ref.partition("#")
    target = (base.parent / file_part).resolve() if file_part else base
    node = _load(target)
    for key in [k for k in pointer.split("/") if k]:
        node = node[key]
    return node, target


def _documented_operations() -> set[tuple[str, str]]:
    root = CONTRACTS_DIR / "openapi.yaml"
    operations = set()
    for path, item in _load(root)["paths"].items():
        if "$ref" in item:
            item, _ = _resolve(item["$ref"], root)
        operations |= {(method.upper(), path) for method in item if method in HTTP_METHODS}
    return operations


def _served_operations() -> set[tuple[str, str]]:
    return {
        (method.upper(), path)
        for path, item in app.openapi()["paths"].items()
        if path.startswith(API_PREFIX)
        for method in item
        if method in HTTP_METHODS
    }


def test_every_served_endpoint_has_a_contract():
    missing = _served_operations() - _documented_operations()
    assert not missing, f"Endpoints with no contract in contracts/: {sorted(missing)}"


def test_every_contract_matches_a_served_endpoint():
    stale = _documented_operations() - _served_operations()
    assert not stale, f"Contracts for endpoints that no longer exist: {sorted(stale)}"


def test_every_ref_resolves():
    def walk(node, source: Path):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref":
                    _resolve(value, source)  # raises KeyError / FileNotFoundError if broken
                else:
                    walk(value, source)
        elif isinstance(node, list):
            for value in node:
                walk(value, source)

    for path in CONTRACTS_DIR.rglob("*.yaml"):
        walk(_load(path), path)
