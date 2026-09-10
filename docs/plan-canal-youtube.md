# Plan para monetizar un canal de Shorts

Guía operativa para pasar de "tengo el generador andando" a "el canal cobra".
Escrita para este proyecto y este pipeline, con los números verificados en
agosto de 2026.

---

## Lo primero: 30 por día no funciona

No es un problema técnico. Tu máquina puede con eso — a 7 minutos por video son
3,5 horas de cómputo, entra en una noche. El problema es que **30 videos
diarios de contenido generado es exactamente el patrón que YouTube penaliza**.

Tres datos que se contradicen con ese plan:

| Dato | Realidad |
|---|---|
| Política de "contenido no auténtico" | Apunta a material masivo, repetitivo y con plantilla. El sistema es de tres avisos: advertencia, suspensión de 90 días, expulsión del programa de socios |
| Señal que dispara la revisión | Publicar muchas veces por día sin variación. Ningún humano sube 12 videos diarios |
| Tope diario por canal | YouTube no lo publica, pero los reportes de la comunidad ubican a los canales nuevos entre **10 y 20 subidas por día** |

La recomendación general para no caer en detección de spam es **2 a 3 videos
por día**, no lotes grandes.

**Entonces el objetivo cambia:** no es maximizar cantidad, es publicar la
cantidad máxima que no active la penalización. Ese número es 3 por día.

Suena a menos, pero: 3 diarios son **90 por mes**. Con este pipeline eso son
unos 20 minutos de render por día. El cuello de botella nunca fue tu máquina.

---

## Qué determina que te paguen tarifas de Estados Unidos

Dos cosas, y ninguna es dónde esté tu servidor ni de qué país sea tu cuenta.

**1. El idioma del contenido.** Los anunciantes pagan por llegar a un mercado.
Video en inglés con audiencia estadounidense cobra entre 4 y 6 veces más que el
mismo video en español con audiencia latinoamericana. Ya estás generando en
inglés, así que esto está resuelto.

**2. Que el contenido le interese a ese público.** El algoritmo muestra tus
Shorts a quien tenga más probabilidad de verlos completos. Si tu retención es
buena entre espectadores de Estados Unidos, ahí se queda la distribución.

Lo que **no** influye: dónde corra el generador, qué IP suba el video, ni desde
qué país esté registrada la cuenta. Podés operar todo desde Argentina.

---

## Paso a paso

### Fase 1 — Preparar el canal (una vez, 1 hora)

1. **Creá el canal** con una cuenta de Google propia. No compres cuentas: te lo
   terminan y perdés lo pagado.
2. **Verificá con teléfono** en `youtube.com/verify`. Sin esto quedás con
   límites más bajos de subida y de duración.
3. **Activá la verificación en dos pasos** en la cuenta de Google. Es requisito
   del programa de socios, mejor resolverlo ahora.
4. **Definí un nicho y sostenelo.** Un canal sobre un tema concreto retiene
   mejor y se lee como auténtico. Los seis videos que ya tenés apuntan a fraude
   digital e identidad — ese es tu nicho, no lo mezcles.
5. **Completá el canal**: foto, banner, descripción, una lista de reproducción.
   Un canal vacío con 90 videos subidos por API se ve automatizado.

### Fase 2 — Publicar a mano las primeras dos semanas

Sí, a mano. Dos razones concretas:

- Un canal nuevo que arranca con subidas por API a ritmo constante es el perfil
  exacto que se revisa. Un canal con historial se revisa menos.
- Vas a necesitar los datos de retención de los primeros videos para saber qué
  funciona antes de automatizar la producción de 90 mensuales.

Cadencia: **1 a 2 por día durante 14 días**. Mirá qué pasa en YouTube Studio,
sobre todo la curva de retención y el porcentaje de espectadores de Estados
Unidos.

### Fase 3 — Automatizar la subida (gratis, con la API de YouTube)

Ya está construido en `tools/youtube_upload.py` y `tools/daily_batch.py`. No
cuesta nada: la API oficial es gratuita, solo hay que darse de alta.

**Preparación, una sola vez (~15 minutos):**

1. Creá un proyecto en <https://console.cloud.google.com>
2. *APIs y servicios → Biblioteca* → buscá **YouTube Data API v3** → Habilitar
3. *APIs y servicios → Pantalla de consentimiento OAuth*: tipo **Externo**,
   completá nombre de la app y tu email. En la sección de permisos agregá el
   scope `https://www.googleapis.com/auth/youtube.upload`
4. En esa misma pantalla, poné el estado de publicación en **"En producción"**
   (botón *Publicar aplicación*). **No la dejes en "Prueba".**
5. *Credenciales → Crear credenciales → ID de cliente de OAuth →
   Aplicación de escritorio*
6. Descargá el JSON y guardalo como `secrets/client_secret.json`
7. Autorizá una vez:

```bash
./.venv/bin/python tools/youtube_upload.py auth
```

> **El paso 4 no es opcional.** Google expira a los **7 días** los refresh
> tokens de las apps en estado "Prueba" con tipo Externo. Si la dejás así, la
> automatización se corta cada semana y hay que volver a autorizar a mano. En
> "En producción" el token no caduca.
>
> Al autorizar vas a ver una pantalla de **app no verificada**: se pasa con
> *Configuración avanzada → Ir a `<app>` (no seguro)*. Es esperable — es tu
> propia app accediendo a tu propio canal, y la verificación de Google solo
> hace falta cuando otras personas van a usarla.

El paso 7 abre el navegador para que inicies sesión vos. Queda un token en
`secrets/youtube_token.json` que se renueva solo.

**Producir y subir la tanda:**

```bash
./.venv/bin/python tools/daily_batch.py --count 10 --spread-hours 14 --privacy private
```

Cuando estés conforme con lo que produce, cambiá a `--privacy public`.

El default es `private` a propósito: una tanda mal configurada publica material
malo en un canal real, y eso no se deshace. Revisá los primeros lotes en Studio
antes de abrir la llave.

**Sobre la cuota:** el costo por subida cambió hace poco y las fuentes se
contradicen — unas dicen 1.600 unidades por video (6 diarios con la cuota
gratis), otras que bajó a ~100 unidades (100 diarios). Verificalo en tu consola
de Google Cloud. Con 10 diarios el valor bajo te alcanza; si rige el de 1.600,
la cuota gratis solo da para 6 y hay que pedir ampliación.

**Qué pasa si un video falla:** la tanda sigue con el siguiente. El tema se
marca como usado recién cuando el video existe, así un fallo no lo quema. El
estado vive en `storage/batch-state.json`.

### Fase 4 — Llegar a la monetización

Necesitás una de estas dos combinaciones:

| Nivel | Requisitos |
|---|---|
| Acceso anticipado | 500 subs + 3 videos públicos en 90 días + 3M vistas de Shorts en 90 días |
| Completo (con publicidad) | 1.000 subs + **10M vistas de Shorts en 90 días** |

La cuenta cruda: a 3 videos diarios son 270 en 90 días. Para llegar a 10
millones necesitás un promedio de **37.000 vistas por video**. Eso no se logra
con volumen, se logra si algunos videos explotan y arrastran al resto.

Por eso la retención importa más que la cantidad, y por eso el pre-prompt del
proyecto está construido alrededor de esa métrica.

---

## ¿Necesitás un servidor?

**Al principio no.** Tu M1 rinde unos 7 minutos por video de 60 segundos. Tres
videos diarios son 21 minutos de máquina. No justifica pagar nada.

Conviene un servidor cuando se cumpla alguna de estas:

- Querés que genere con la laptop apagada
- La máquina te queda inutilizable mientras renderiza y eso te molesta
- Pasás de un canal a varios

Si llega ese momento, lo que este pipeline necesita es **CPU, no GPU** — el
render es ffmpeg y composición, y ya funciona con `h264_videotoolbox` o
`libx264`. Un VPS de 4 a 8 núcleos alcanza, entre 20 y 40 dólares mensuales.
El repo trae `docker-compose.release.yml`, así que el despliegue es copiar el
`config.toml` y levantar el contenedor.

Para programarlo, un `cron` que corra el generador tres veces al día:

```bash
0 8,14,20 * * * cd /ruta/MoneyPrinterTurbo && ./.venv/bin/python cli.py --video-script "$(./.venv/bin/python tools/pick_script.py "TEMA" --quiet)" ... >> /var/log/mpt.log 2>&1
```

Ojo con dos cosas al automatizar del todo: si el guion sale mal nadie lo revisa
antes de publicarse, y si publicás siempre a la misma hora exacta el patrón se
nota. Conviene dejar un paso de revisión humana al menos al principio.

---

## Costos reales por mes

| Ítem | Costo |
|---|---|
| Guiones (Groq capa gratis) | 0 |
| Material (Pexels / Pixabay) | 0 |
| Voz (Edge TTS) | 0 |
| Render (tu máquina) | 0 |
| Subida automática (API de YouTube) | 0 |
| Servidor (opcional, después) | 20 a 40 USD |

**Todo el pipeline es gratis.** El único gasto posible es el servidor, y recién
si querés que genere con la laptop apagada.

---

## Qué esperar, con honestidad

- **Mes 1**: entre 0 y 1.000 vistas por video. Estás calibrando qué temas
  retienen.
- **Mes 2 y 3**: si algo funciona, se nota acá. Un video que rompe arrastra
  suscriptores al resto del canal.
- **Monetización**: entre 3 y 6 meses si el contenido funciona. Puede no pasar
  nunca. La mayoría de los canales de este tipo no llegan.
- **Ingresos al llegar**: con audiencia estadounidense, 10M de vistas de Shorts
  rinden aproximadamente entre 1.000 y 1.800 dólares.

**El camino más rápido a los primeros dólares no es la publicidad.** Afiliación
te paga desde la primera venta, sin esperar los 1.000 suscriptores. Tu nicho de
fraude digital conecta directo con gestores de contraseñas, VPNs y cursos de
seguridad. Poné el enlace en la descripción y el canal fijado desde el video
número uno.

---

## Los tres errores que matan estos canales

1. **Volumen sobre calidad.** Es lo que activa la política de contenido no
   auténtico. Tres buenos superan a treinta iguales.
2. **Publicar sin mirar.** Un guion que salió mal, un dato inventado sobre una
   empresa real, o material con marca de agua ajena. Revisá antes de subir.
3. **Cambiar de nicho cada semana.** El algoritmo necesita entender a quién
   mostrarte. Un canal sobre un tema retiene; uno sobre todo, no retiene a
   nadie.

---

## Fuentes

- [Programa de socios de YouTube: elegibilidad](https://support.google.com/youtube/answer/72851?hl=es-419)
- [YouTube clarifica las reglas sobre contenido no auténtico — Social Media Today](https://www.socialmediatoday.com/news/youtube-clarifies-monetization-update-inauthentic-repeated-content/752892/)
- [Límites de subida de YouTube 2026 — SolutionBlades](https://www.solutionblades.com/en-us/education/youtube-video-upload-limit-per-day-the-actual-rules-in-2026/)
- [Cuota de la API de YouTube 2026 — Phyllo](https://www.getphyllo.com/post/youtube-api-limits-how-to-calculate-api-usage-cost-and-fix-exceeded-api-quota)
- [Auto-publicar Shorts por API — Upload-Post](https://www.upload-post.com/how-to/auto-post-youtube-shorts/)
