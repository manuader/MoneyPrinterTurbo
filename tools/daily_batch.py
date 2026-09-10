"""
Genera y publica una tanda diaria de Shorts.

Para cada video: elige un tema sin usar, genera el guion con pick_script,
renderiza, y deja que el pipeline lo suba solo (upload_post_auto_upload).

    python tools/daily_batch.py --count 10 --spread-hours 14
    python tools/daily_batch.py --count 1              # una sola pasada, para cron
    python tools/daily_batch.py --count 3 --dry-run    # sin renderizar ni subir

El estado vive en storage/batch-state.json: qué temas ya se usaron y qué se
generó cada día. Se puede cortar la corrida y retomarla sin repetir temas.
"""

import argparse
import json
import os
import random
import subprocess
import sys
import time
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(ROOT)

TOPICS_FILE = os.path.join(ROOT, "tools", "topics.txt")
STATE_FILE = os.path.join(ROOT, "storage", "batch-state.json")
PYTHON = os.path.join(ROOT, ".venv", "bin", "python")

# Ajustes de render compartidos por toda la tanda. Se mantienen aquí y no en el
# cron para que cambiarlos no implique editar la crontab.
RENDER_ARGS = [
    "--video-language", "en-US",
    "--voice-name", "en-US-AndrewNeural",
    "--subtitle-position", "center",
    "--font-name", "BeVietnamPro-Bold.ttf",
    "--font-size", "58",
    "--stroke-width", "3",
    "--video-clip-duration", "3",
    "--n-threads", "8",
]


def load_state() -> dict:
    if not os.path.isfile(STATE_FILE):
        return {"used_topics": [], "runs": []}
    try:
        with open(STATE_FILE, encoding="utf-8") as fp:
            return json.load(fp)
    except Exception:
        # Un estado corrupto no puede frenar la producción: se empieza de cero
        # y el archivo se reescribe al final de la corrida.
        print("state file unreadable, starting fresh", file=sys.stderr)
        return {"used_topics": [], "runs": []}


def save_state(state: dict) -> None:
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fp:
        json.dump(state, fp, indent=2, ensure_ascii=False)
    os.replace(tmp, STATE_FILE)


def load_topics(topics_file: str = TOPICS_FILE) -> list[dict]:
    """
    Lee topics.txt. Cada línea es `tema | términos de búsqueda`.

    Los términos van escritos a mano junto al tema porque son la parte más
    frágil del pipeline: los generados automáticamente devuelven material
    genérico que no acompaña al guion.
    """
    if not os.path.isfile(topics_file):
        raise SystemExit(f"missing topics file: {topics_file}")

    topics = []
    for line in open(topics_file, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        subject, _, terms = line.partition("|")
        subject, terms = subject.strip(), terms.strip()
        if subject and terms:
            topics.append({"subject": subject, "terms": terms})
    if not topics:
        raise SystemExit(f"no usable topics in {topics_file}")
    return topics


def pick_topics(count: int, state: dict, topics_file: str = TOPICS_FILE) -> list[dict]:
    """
    Elige temas sin repetir. Al agotarse la lista el ciclo vuelve a empezar.

    Repetir un tema no es fatal — el guion sale distinto igual — pero conviene
    agotar la variedad disponible antes de reciclar.
    """
    topics = load_topics(topics_file)
    used = set(state.get("used_topics", []))
    fresh = [t for t in topics if t["subject"] not in used]

    if len(fresh) < count:
        print(f"topic pool exhausted ({len(fresh)} left), recycling", file=sys.stderr)
        state["used_topics"] = []
        fresh = topics

    random.shuffle(fresh)
    return fresh[:count]


def generate_script(subject: str) -> str | None:
    result = subprocess.run(
        [PYTHON, os.path.join(ROOT, "tools", "pick_script.py"),
         subject, "--candidates", "6", "--quiet"],
        capture_output=True, text=True, cwd=ROOT,
    )
    script = result.stdout.strip()
    if result.returncode != 0 or not script:
        print(f"  script failed: {result.stderr.strip()[:200]}", file=sys.stderr)
        return None
    return script


def render_video(script: str, terms: str) -> str | None:
    """Renderiza y devuelve la ruta del MP4. La subida la dispara el pipeline."""
    result = subprocess.run(
        [PYTHON, os.path.join(ROOT, "cli.py"),
         "--video-script", script, "--video-terms", terms, *RENDER_ARGS],
        capture_output=True, text=True, cwd=ROOT, stdin=subprocess.DEVNULL,
    )
    for line in result.stdout.splitlines():
        if '"videos"' in line:
            try:
                return json.loads(line)["result"]["videos"][0]
            except Exception:
                pass
    print(f"  render failed: {result.stderr.strip()[-300:]}", file=sys.stderr)
    return None


def build_metadata(subject: str, script: str) -> dict:
    """
    Arma título, descripción y tags a partir del tema y el guion.

    El título sale de la primera oración del guion, no del tema: esa oración es
    el hook, ya está escrita para enganchar, y el tema es una instrucción
    interna que suele leerse como descripción de tarea.
    """
    first_sentence = script.split(".")[0].strip()
    title = first_sentence if 15 <= len(first_sentence) <= 90 else subject
    if not title.endswith(("?", "!", ".")):
        title += "..."

    description = (
        f"{script[:400].strip()}\n\n"
        "This is a fictional scenario, not a report of real events.\n\n"
        "#Shorts"
    )
    return {
        "title": f"{title} #Shorts"[:100],
        "description": description,
        "tags": ["shorts", "story", "truecrime", "scam", "ai"],
    }


def upload_video(video_path: str, meta: dict, privacy: str) -> str | None:
    sys.path.insert(0, os.path.join(ROOT, "tools"))
    from youtube_upload import upload

    return upload(
        video_path,
        title=meta["title"],
        description=meta["description"],
        tags=meta["tags"],
        privacy=privacy,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=10)
    parser.add_argument(
        "--spread-hours",
        type=float,
        default=0,
        help=(
            "reparte la tanda a lo largo de estas horas. 0 los hace seguidos. "
            "Publicar diez videos en diez minutos es el patrón que dispara la "
            "detección de spam; repartirlos lo evita"
        ),
    )
    parser.add_argument(
        "--privacy",
        default="private",
        choices=["private", "unlisted", "public", "none"],
        help=(
            "visibilidad de la subida, o 'none' para solo generar sin subir. "
            "Default private: una tanda mal configurada no debería publicarse "
            "sola en un canal real"
        ),
    )
    parser.add_argument(
        "--topics-file",
        default=TOPICS_FILE,
        help="lista de temas a usar; permite tandas tematicas separadas",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    state = load_state()
    topics = pick_topics(args.count, state, args.topics_file)
    started = datetime.now(timezone.utc).isoformat()

    # El intervalo se calcula sobre count-1 huecos: el primer video sale ya.
    gap = (args.spread_hours * 3600 / max(1, args.count - 1)) if args.spread_hours else 0

    produced = []
    for index, topic in enumerate(topics, 1):
        print(f"[{index}/{len(topics)}] {topic['subject'][:70]}")

        if args.dry_run:
            print(f"  terms: {topic['terms'][:70]}")
            produced.append({"subject": topic["subject"], "video": "(dry-run)"})
            state.setdefault("used_topics", []).append(topic["subject"])
            continue

        script = generate_script(topic["subject"])
        if not script:
            continue

        video = render_video(script, topic["terms"])
        if not video:
            continue

        print(f"  -> {video}")
        record = {"subject": topic["subject"], "video": video}

        if args.privacy != "none":
            meta = build_metadata(topic["subject"], script)
            try:
                video_id = upload_video(video, meta, args.privacy)
            except SystemExit as exc:
                # Falta de credenciales: cortar la tanda entera, porque los
                # videos siguientes fallarían igual y sin subirse.
                print(f"\n{exc}", file=sys.stderr)
                save_state(state)
                return 1
            if video_id:
                record["youtube_id"] = video_id
                record["title"] = meta["title"]

        produced.append(record)
        # El tema se marca recién cuando el video existe, así un fallo lo deja
        # disponible para la próxima corrida.
        state.setdefault("used_topics", []).append(topic["subject"])
        save_state(state)

        if gap and index < len(topics):
            # Un intervalo exacto se lee como automatización. El jitter de ±20%
            # cuesta nada y rompe la regularidad.
            wait = gap * random.uniform(0.8, 1.2)
            print(f"  waiting {wait / 60:.0f} min before the next one")
            time.sleep(wait)

    state.setdefault("runs", []).append({
        "started": started,
        "finished": datetime.now(timezone.utc).isoformat(),
        "requested": args.count,
        "produced": len(produced),
        "videos": produced,
    })
    state["runs"] = state["runs"][-30:]
    save_state(state)

    print(f"\n{len(produced)}/{args.count} videos produced")
    return 0 if produced else 1


if __name__ == "__main__":
    raise SystemExit(main())
