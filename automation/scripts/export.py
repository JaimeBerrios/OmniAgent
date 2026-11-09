#!/usr/bin/env python3

import json
from pathlib import Path
from datetime import datetime, timezone

import requests

ROOT = Path(__file__).resolve().parents[2]
ENV = ROOT / "infrastructure/.env"
LOCAL = ROOT / "automation/workflows/whatsapp.json"
BACKUPS = ROOT / "automation/backups"

values = {}
for line in ENV.read_text().splitlines():
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        values[k.strip()] = v.strip().strip('"').strip("'")

key = values.get("N8N_PUBLIC_API_KEY")
workflow_id = values.get("N8N_WORKFLOW_ID")

if not key or not workflow_id:
    raise SystemExit("Faltan N8N_PUBLIC_API_KEY o N8N_WORKFLOW_ID")

response = requests.get(
    f"http://127.0.0.1:5678/api/v1/workflows/{workflow_id}",
    headers={"X-N8N-API-KEY": key},
    timeout=20,
)
response.raise_for_status()

remote = response.json()

BACKUPS.mkdir(parents=True, exist_ok=True)

timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
destination = BACKUPS / f"whatsapp-production-{timestamp}.json"

destination.write_text(
    json.dumps(remote, indent=2, ensure_ascii=False) + "\n",
    encoding="utf-8",
)

local = json.loads(LOCAL.read_text())

remote_nodes = {
    node.get("name"): node for node in remote.get("nodes", [])
}
local_nodes = {
    node.get("name"): node for node in local.get("nodes", [])
}

print("=== EXPORTACIÓN ===")
print("Archivo:", destination.relative_to(ROOT))
print("ID:", remote.get("id"))
print("Nombre remoto:", remote.get("name"))
print("Activo:", remote.get("active"))
print("Nodos remotos:", len(remote_nodes))
print("Nodos locales:", len(local_nodes))

print("\n=== DIFERENCIAS DE NODOS ===")

print("Solo en producción:")
for name in sorted(remote_nodes.keys() - local_nodes.keys()):
    print(" +", name)

print("Solo en local:")
for name in sorted(local_nodes.keys() - remote_nodes.keys()):
    print(" -", name)

print("\n=== DIFERENCIAS DE CONFIGURACIÓN ===")

for name in sorted(remote_nodes.keys() & local_nodes.keys()):
    remote_node = remote_nodes[name]
    local_node = local_nodes[name]

    differences = []

    for field in ("type", "typeVersion", "parameters", "position"):
        if remote_node.get(field) != local_node.get(field):
            differences.append(field)

    if differences:
        print(f"{name}: {', '.join(differences)}")

print("\nConexiones idénticas:",
      remote.get("connections") == local.get("connections"))

print("\nEXPORTACIÓN COMPLETADA. PRODUCCIÓN NO MODIFICADA.")
