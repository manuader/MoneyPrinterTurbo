"""
Sube videos a YouTube con la API oficial. Sin costo y sin intermediarios.

Preparación, una sola vez:

  1. Creá un proyecto en https://console.cloud.google.com
  2. Habilitá "YouTube Data API v3"
  3. Pantalla de consentimiento OAuth: tipo Externo, y agregá el scope
     .../auth/youtube.upload
  4. Poné el estado de publicación en "En producción", NO en "Prueba"
  5. Credenciales -> Crear -> ID de cliente OAuth -> Aplicación de escritorio
  6. Descargá el JSON como  secrets/client_secret.json
  7. Autorizá una vez:   python tools/youtube_upload.py auth

El paso 4 no es opcional para una automatización diaria: Google expira a los
7 días los refresh tokens de las apps en estado "Prueba" con tipo Externo. En
"En producción" el token no caduca, y como la app no está verificada vas a ver
una pantalla de advertencia al autorizar — se pasa con "Configuración
avanzada" -> "Ir a <app> (no seguro)". Es tu propia app accediendo a tu propio
canal.

El paso 7 abre el navegador para que inicies sesión vos. El token queda en
secrets/youtube_token.json y se renueva solo; no hay que repetirlo.

Subir:

  python tools/youtube_upload.py upload video.mp4 --title "..." --privacy private

IMPORTANTE: el default es `private`. Es a propósito — una tanda mal configurada
publica basura en un canal real y eso no se deshace. Pasá `--privacy public`
cuando estés conforme con lo que produce el pipeline.
"""

import argparse
import os
import random
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SECRETS_DIR = os.path.join(ROOT, "secrets")
CLIENT_SECRET = os.path.join(SECRETS_DIR, "client_secret.json")
TOKEN_FILE = os.path.join(SECRETS_DIR, "youtube_token.json")

# Solo el permiso de subida. Pedir menos scopes reduce el daño si el token se
# filtra: con este no se puede leer, borrar ni modificar nada del canal.
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

# 22 = People & Blogs. Sirve como default seguro para narrativa corta.
DEFAULT_CATEGORY_ID = "22"


def _load_credentials():
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials

    if not os.path.isfile(TOKEN_FILE):
        raise SystemExit(
            f"no hay token en {TOKEN_FILE}\n"
            f"corré primero:  python tools/youtube_upload.py auth"
        )

    creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        _save_credentials(creds)
    return creds


def _save_credentials(creds) -> None:
    os.makedirs(SECRETS_DIR, exist_ok=True)
    with open(TOKEN_FILE, "w", encoding="utf-8") as fp:
        fp.write(creds.to_json())
    # El token da permiso de subida sobre el canal: no debe quedar legible
    # para otros usuarios de la máquina.
    os.chmod(TOKEN_FILE, 0o600)


def authorize() -> int:
    """Flujo OAuth interactivo. Lo corre el usuario, una sola vez."""
    from google_auth_oauthlib.flow import InstalledAppFlow

    if not os.path.isfile(CLIENT_SECRET):
        raise SystemExit(
            f"falta {CLIENT_SECRET}\n"
            f"descargalo desde Google Cloud Console (ID de cliente OAuth, "
            f"tipo Aplicación de escritorio)"
        )

    # El JSON de un cliente "web" se descarga igual y parece correcto, pero
    # run_local_server elige un puerto al azar que no está registrado como
    # redirect_uri, así que la autorización falla con un redirect_uri_mismatch
    # que no explica nada. Se detecta antes de abrir el navegador.
    import json

    with open(CLIENT_SECRET, encoding="utf-8") as fp:
        client_config = json.load(fp)
    if "installed" not in client_config:
        found = ", ".join(client_config.keys()) or "(vacío)"
        raise SystemExit(
            f"{CLIENT_SECRET} no es un cliente de escritorio.\n"
            f"El JSON empieza con: {found}  (debería ser 'installed')\n\n"
            f"En Google Cloud Console: Credenciales -> Crear credenciales ->\n"
            f"ID de cliente de OAuth -> tipo 'Aplicación de escritorio'.\n"
            f"El tipo 'Aplicación web' no sirve para este flujo."
        )

    flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
    # access_type=offline + prompt=consent fuerza la entrega de refresh_token,
    # que es lo que permite subir sin volver a abrir el navegador nunca más.
    creds = flow.run_local_server(
        port=0, access_type="offline", prompt="consent"
    )
    _save_credentials(creds)
    print(f"autorizado, token guardado en {TOKEN_FILE}")
    return 0


def upload(
    video_path: str,
    title: str,
    description: str = "",
    tags: list[str] | None = None,
    privacy: str = "private",
    category_id: str = DEFAULT_CATEGORY_ID,
) -> str | None:
    """Sube un video y devuelve su ID, o None si falló."""
    from googleapiclient.discovery import build
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    if not os.path.isfile(video_path):
        print(f"no existe el archivo: {video_path}", file=sys.stderr)
        return None

    youtube = build("youtube", "v3", credentials=_load_credentials())
    body = {
        "snippet": {
            # El título de YouTube corta en 100 caracteres.
            "title": title[:100],
            "description": description[:5000],
            "tags": (tags or [])[:15],
            "categoryId": category_id,
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
            # Declarar el material sintético es obligatorio para contenido
            # generado con IA. Omitirlo es lo que convierte una advertencia
            # de política en una sanción.
            "containsSyntheticMedia": True,
        },
    }

    media = MediaFileUpload(video_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(
        part="snippet,status", body=body, media_body=media
    )

    # Subida reanudable con reintentos: un corte de red a mitad de archivo es
    # normal y no debería costar el video entero.
    response, error_count = None, 0
    while response is None:
        try:
            _status, response = request.next_chunk()
        except HttpError as exc:
            if exc.resp.status in (500, 502, 503, 504) and error_count < 5:
                error_count += 1
                sleep_for = (2**error_count) + random.random()
                print(f"  error {exc.resp.status}, reintento en {sleep_for:.0f}s",
                      file=sys.stderr)
                time.sleep(sleep_for)
                continue
            print(f"  fallo de subida: {exc}", file=sys.stderr)
            return None
        except Exception as exc:
            print(f"  fallo de subida: {exc}", file=sys.stderr)
            return None

    video_id = response.get("id")
    print(f"  subido: https://youtu.be/{video_id}  ({privacy})")
    return video_id


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("auth", help="autorizar una vez con el navegador")

    up = sub.add_parser("upload", help="subir un video")
    up.add_argument("video")
    up.add_argument("--title", required=True)
    up.add_argument("--description", default="")
    up.add_argument("--tags", default="")
    up.add_argument(
        "--privacy",
        default="private",
        choices=["private", "unlisted", "public"],
        help="default private, a propósito",
    )

    args = parser.parse_args()
    if args.command == "auth":
        return authorize()

    tags = [t.strip() for t in args.tags.split(",") if t.strip()]
    video_id = upload(
        args.video,
        title=args.title,
        description=args.description,
        tags=tags,
        privacy=args.privacy,
    )
    return 0 if video_id else 1


if __name__ == "__main__":
    raise SystemExit(main())
