import importlib.util
import shutil
import unicodedata

TOOLS = {
    "notes": {"name": "Notas locales", "purpose": "Organizar ideas y encargos en Markdown", "command": None},
    "ffmpeg": {"name": "FFmpeg", "purpose": "Recortar y convertir video/audio", "command": "ffmpeg", "url": "https://ffmpeg.org/download.html"},
    "blender": {"name": "Blender", "purpose": "Modelado, escenas y render 3D", "command": "blender", "url": "https://www.blender.org/download/"},
    "canva": {"name": "Canva", "purpose": "Diseño de piezas gráficas", "command": None, "url": "https://www.canva.com/", "connection": "Cuenta y conector por implementar"},
    "hermes": {"name": "Hermes", "purpose": "Motor conversacional y herramientas", "command": "hermes", "url": "https://hermes-agent.nousresearch.com/", "connection": "Integración de permisos ARKOS pendiente"},
    "home_assistant": {"name": "Home Assistant", "purpose": "Controlar dispositivos compatibles expuestos por el usuario", "command": None, "url": "https://www.home-assistant.io/", "connection": "Servidor, credenciales y MCP por configurar"},
    "kokoro": {"name": "Kokoro", "purpose": "Voz local; requiere modelos y dependencias", "module": "kokoro", "command": None},
    "faster_whisper": {"name": "faster-whisper", "purpose": "Transcripción local; requiere modelos y dependencias", "module": "faster_whisper", "command": None},
}


def inventory():
    result = {}
    for key, tool in TOOLS.items():
        item = dict(tool)
        item["path"] = shutil.which(tool["command"]) if tool.get("command") else None
        if key == "notes":
            item["status"] = "ready"
        elif tool.get("module"):
            item["status"] = "package_detected" if importlib.util.find_spec(tool["module"]) else "missing_package"
        elif item.get("connection"):
            item["status"] = "requires_connection" if not item["path"] else "detected_requires_integration"
        else:
            item["status"] = "detected" if item["path"] else "missing"
        result[key] = item
    return result


def propose(goal):
    """Deterministic pilot routing, deliberately not an LLM or arbitrary executor."""
    normalized = unicodedata.normalize("NFKD", goal.lower())
    text = "".join(c for c in normalized if not unicodedata.combining(c))
    if any(word in text for word in ("video", "audio", "recortar")):
        choices, follow_up = ["ffmpeg", "blender"], "Indica el archivo, inicio y duración; puedo preparar un recorte sin sobrescribir el original."
    elif any(word in text for word in ("lampara", "luces", "alexa", "casa")):
        choices, follow_up = ["home_assistant"], "Conecta Home Assistant y elige qué dispositivos podrá controlar ARKOS."
    elif any(word in text for word in ("3d", "arquitect", "render")):
        choices, follow_up = ["blender"], "Indica dimensiones, referencias y formato de entrega."
    elif any(word in text for word in ("diseno", "logo", "cartel")):
        choices, follow_up = ["canva", "blender"], "Define tamaño, estilo y destino; te propongo una pieza y una variante."
    else:
        choices, follow_up = ["notes", "hermes"], "Puedo guardar el encargo ahora. Para ejecutarlo, define el resultado y conecta la herramienta necesaria."
    available = inventory()
    return {"goal": goal, "tools": [{"id": key, **available[key]} for key in choices], "next_step": follow_up,
            "scope": "Propuesta local basada en reglas. Las conexiones ausentes no se instalan automáticamente."}
