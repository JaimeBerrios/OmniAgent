from html import escape

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()

CONTACT = "ingjaime1999@gmail.com"


def page(title: str, content: str) -> HTMLResponse:
    return HTMLResponse(f"""
    <!DOCTYPE html>
    <html lang="es">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <title>{escape(title)} | OmniAgent</title>
        <style>
            body {{
                font-family: Arial, sans-serif;
                line-height: 1.7;
                max-width: 780px;
                margin: 50px auto;
                padding: 0 24px;
                color: #243044;
            }}
            h1, h2 {{ color: #173b70; }}
            a {{ color: #1769aa; }}
        </style>
    </head>
    <body>
        <h1>{escape(title)}</h1>
        {content}
        <hr>
        <p>Contacto: <a href="mailto:{CONTACT}">{CONTACT}</a></p>
    </body>
    </html>
    """)


@router.get("/privacy", response_class=HTMLResponse)
def privacy():
    return page("Política de privacidad", """
        <p>OmniAgent es una plataforma de gestión de conversaciones
        y automatización de comunicaciones con clientes.</p>

        <h2>Información tratada</h2>
        <p>La plataforma puede tratar identificadores de clientes,
        nombres, mensajes, información de conversaciones,
        canales de comunicación y fechas de registro.</p>
        <p>Para sus usuarios administrativos, puede almacenar
        direcciones de correo electrónico y credenciales
        protegidas mediante hashes de contraseña.</p>

        <h2>Finalidad</h2>
        <p>Esta información se utiliza para gestionar conversaciones,
        organizar la atención al cliente y ejecutar automatizaciones
        relacionadas con los servicios de OmniAgent.</p>

        <h2>Servicios de terceros</h2>
        <p>OmniAgent puede integrarse con WhatsApp Business Platform,
        proporcionada por Meta, para procesar comunicaciones
        realizadas mediante dicho canal.</p>

        <h2>Seguridad</h2>
        <p>La plataforma implementa mecanismos de autenticación
        y control de acceso. Ningún sistema puede garantizar
        seguridad absoluta.</p>

        <h2>Derechos y solicitudes</h2>
        <p>Para consultas sobre información personal, acceso,
        corrección o eliminación de datos, escribe a
        <a href="mailto:ingjaime1999@gmail.com">
        ingjaime1999@gmail.com</a>.</p>
    """)


@router.get("/data-deletion", response_class=HTMLResponse)
def data_deletion():
    return page("Solicitud de eliminación de datos", """
        <p>Los usuarios pueden solicitar la eliminación de
        información personal tratada mediante OmniAgent.</p>

        <h2>Procedimiento</h2>
        <ol>
            <li>Envía un correo a
            <a href="mailto:ingjaime1999@gmail.com">
            ingjaime1999@gmail.com</a>.</li>
            <li>Utiliza el asunto:
            Solicitud de eliminación de datos - OmniAgent.</li>
            <li>Indica el canal de comunicación y los datos
            necesarios para localizar tu información.</li>
            <li>Se verificará la solicitud y se evaluará
            la eliminación correspondiente, considerando
            las obligaciones legales aplicables.</li>
        </ol>

        <p>No envíes contraseñas ni información sensible
        innecesaria para identificar tu solicitud.</p>
    """)
