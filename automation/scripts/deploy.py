#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

import requests

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / "infrastructure/.env"
BACKUPS = ROOT / "automation/backups"
WORKFLOWS = ROOT / "automation/workflows"


def load_env():
    values = {}
    for line in ENV.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            values[k.strip()] = v.strip().strip('"').strip("'")
    return values


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workflow", required=True)
    parser.add_argument("--id", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    path = WORKFLOWS / f"{args.workflow}.json"

    if not path.is_file():
        sys.exit("Workflow local inexistente")

    values = load_env()
    key = values.get("N8N_PUBLIC_API_KEY")
    workflow_id_key = (
        "N8N_MESSENGER_WORKFLOW_ID"
        if args.workflow == "messenger"
        else "N8N_WORKFLOW_ID"
    )
    configured_id = values.get(workflow_id_key)

    if not key or not configured_id:
        sys.exit("Faltan credenciales o ID configurado")

    if args.id != configured_id:
        sys.exit("ID diferente al configurado. Operación cancelada.")

    local = json.loads(path.read_text())

    if str(local.get("id")) != args.id:
        sys.exit("El ID del JSON no coincide. Operación cancelada.")

    headers = {
        "X-N8N-API-KEY": key,
        "Content-Type": "application/json",
    }

    base = "http://127.0.0.1:5678/api/v1"

    response = requests.get(
        f"{base}/workflows/{args.id}",
        headers=headers,
        timeout=20,
    )
    response.raise_for_status()

    remote = response.json()

    if not args.apply:
        print("MODO DE SIMULACIÓN")
        print("Workflow:", local.get("name"))
        print("ID:", args.id)
        print("Activo:", remote.get("active"))
        print("Nodos locales:", len(local.get("nodes", [])))
        print("Nodos producción:", len(remote.get("nodes", [])))
        print("No se modificó producción.")
        print("Para autorizar: añade --apply")
        return

    BACKUPS.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    backup = BACKUPS / f"{args.workflow}-predeploy-{timestamp}.json"

    backup.write_text(
        json.dumps(remote, indent=2, ensure_ascii=False) + "\n"
    )

    payload = {
        "name": local["name"],
        "nodes": local["nodes"],
        "connections": local["connections"],
        "settings": local.get("settings", {}),
    }

    result = requests.put(
        f"{base}/workflows/{args.id}",
        headers=headers,
        json=payload,
        timeout=30,
    )
    result.raise_for_status()

    print("DESPLIEGUE COMPLETADO")
    print("Respaldo:", backup.name)
    print("Workflow:", local["name"])
    print("Estado activo anterior:", remote.get("active"))


if __name__ == "__main__":
    main()
