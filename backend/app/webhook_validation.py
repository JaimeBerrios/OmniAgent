from fastapi import HTTPException


def validate_envelope(payload):
    if not isinstance(payload, dict) or not isinstance(payload.get('entry', []), list):
        raise HTTPException(400, 'Payload inválido')
    for entry in payload.get('entry', []):
        if not isinstance(entry, dict):
            raise HTTPException(400, 'Entrada inválida')
        for key in ('changes', 'messaging'):
            if not isinstance(entry.get(key, []), list):
                raise HTTPException(400, 'Lista de eventos inválida')
        for change in entry.get('changes', []):
            if not isinstance(change, dict) or not isinstance(change.get('value', {}), dict):
                raise HTTPException(400, 'Cambio inválido')
            value = change.get('value', {})
            if not isinstance(value.get('metadata', {}), dict) or not isinstance(value.get('messages', []), list):
                raise HTTPException(400, 'Contenido inválido')
