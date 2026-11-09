#!/usr/bin/env python3

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = ROOT / "automation" / "workflows"


def validate(path):
    errors = []

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return [f"JSON inválido: {exc}"]

    nodes = data.get("nodes")
    connections = data.get("connections")

    if not isinstance(nodes, list):
        return ["El campo nodes debe ser una lista"]

    if not isinstance(connections, dict):
        return ["El campo connections debe ser un objeto"]

    if not data.get("name"):
        errors.append("Falta el nombre del workflow")

    names = [node.get("name") for node in nodes]

    if any(not name for name in names):
        errors.append("Existe un nodo sin nombre")

    if len(names) != len(set(names)):
        errors.append("Hay nombres de nodos duplicados")

    ids = [node.get("id") for node in nodes if node.get("id")]

    if len(ids) != len(set(ids)):
        errors.append("Hay identificadores de nodos duplicados")

    known = set(names)

    for node in nodes:
        if not node.get("type"):
            errors.append(f"Nodo sin tipo: {node.get('name')}")

    for source, outputs in connections.items():
        if source not in known:
            errors.append(f"Origen inexistente: {source}")
            continue

        for branches in outputs.values():
            for branch in branches:
                for connection in branch:
                    target = connection.get("node")

                    if target not in known:
                        errors.append(
                            f"Destino inexistente: {source} -> {target}"
                        )

    return errors


def main():
    files = sorted(WORKFLOWS.glob("*.json"))

    if not files:
        print("No hay workflows en automation/workflows/")
        sys.exit(1)

    failed = False

    for path in files:
        errors = validate(path)

        print(f"\n{path.name}")

        if errors:
            failed = True
            for error in errors:
                print(f"  ERROR: {error}")
        else:
            print("  VALIDACIÓN SUPERADA")

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
