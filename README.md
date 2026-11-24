# Bot de convocatorias de empleo público → Telegram

Revisa los boletines (lunes y jueves, desde tu Mac) y te avisa por Telegram de:

- **Toda España**: plazas de informática de cualquier organismo (también bolsas e interinidades).
- **Asturias**, además: plazas **A1/A2 de oficina** que pidan un grado (administración general,
  gestión, jurídico-administrativo, RR. HH., económico, comunicación…). Nada de C1/C2 ni de puestos
  que exijan otra carrera concreta.

Solo avisa de convocatorias **con el plazo abierto** y **nunca repite** una convocatoria, aunque salga
en dos fuentes (por ejemplo en el BOPA y semanas después en el BOE).

**Fuentes**

| Qué | Cómo |
|---|---|
| BOE, sección II.B | API oficial de datos abiertos (texto completo, cálculo de plazo) |
| 19 boletines autonómicos y 43 provinciales | lector genérico (`fuentes.yaml`) |
| Webs concretas: ayuntamientos, universidades, sanidad, empresas públicas, INCIBE, SEPI… | lector genérico (`fuentes.yaml`) |

El lector genérico entiende RSS, XML/CSV de datos abiertos, páginas HTML y el PDF del día de los
boletines que solo publican así. Desde la portada sigue hasta 2 niveles de enlaces tipo «sumario»,
«último boletín», «empleo», «procesos selectivos» o con la fecha de hoy, y se queda con los anuncios
de empleo. La primera vez que mira una fuente no te manda lo que ya estaba publicado (salvo que el
propio anuncio diga que el plazo sigue abierto); después, un mensaje por cada anuncio nuevo. Si una fuente falla 2 revisiones seguidas,
te avisa una vez para que la revises.

Descarta lo que no abre plazo (listas de admitidos, tribunales, nombramientos, correcciones),
promoción interna, libre designación, concursos de traslados y plazas docentes (universidad y profesorado, que exigen doctorado o Máster de Profesorado).

Cada aviso del BOE trae organismo, plazas, grupo, sistema, etiqueta de titulación (✅ encaja /
⚠️ revisa), fin de plazo aproximado, dónde están las bases y el enlace. Los de boletines y webs
traen el título del anuncio, la etiqueta y el enlace.

## Puesta en marcha (en el Mac)

El bot se ejecuta en tu Mac: **lunes y jueves** a partir de las 9:00. Si ese día el Mac está apagado,
revisa en cuanto lo enciendas (o lo despiertes) y no se pierde nada: recupera todos los BOE pendientes
desde la última vez. Desde una conexión española responden boletines que bloquean a los servidores
de GitHub (BOC de Cantabria, varios BOP de Castilla y León…).

1. **Bot de Telegram**: token de `@BotFather` y tu chat_id (escribe al bot y abre
   `https://api.telegram.org/bot<TOKEN>/getUpdates`).
2. **Python 3.10 o superior** (el de macOS se queda corto): `brew install python@3.12`
3. **Descarga el proyecto en tu carpeta personal** (no en Documentos, Escritorio ni iCloud: macOS no
   deja que las tareas en segundo plano lean esas carpetas):
   ```bash
   cd ~ && git clone https://github.com/adrirodrigar1999/convocatorias-bot.git
   cd convocatorias-bot
   cp .env.example .env      # y pon TELEGRAM_TOKEN y TELEGRAM_CHAT_ID
   ```
4. **Instala la tarea programada**:
   ```bash
   ./scripts/mac/instalar.sh
   .venv/bin/python -m bot.main --prueba-telegram     # te llega un mensaje de prueba
   ```
   Al terminar la instalación arranca la primera revisión: mira 45 días atrás y te avisa de lo que
   siga con plazo abierto, más un resumen por cada boletín o web.

Cómo funciona: launchd lanza `scripts/mac/ejecutar.sh` al iniciar sesión y cada hora. El script
actualiza el código con `git pull` (así te llegan las fuentes que se vayan arreglando) y ejecuta
`python -m bot.main --programado`, que solo trabaja si ha pasado un lunes o jueves (después de las
9:00) desde la última revisión. El resto de veces termina al instante.

- Registro: `logs/bot.log`
- Cambiar días u hora: `DIAS_EJECUCION` y `HORA_EJECUCION` en `.env`
- Forzar una revisión ahora: `.venv/bin/python -m bot.main`
- Quitarlo: `./scripts/mac/desinstalar.sh`
- Empezar de cero (borra los mensajes del chat de las últimas 48 h y todo lo que el bot ha visto):
  `.venv/bin/python -m bot.main --reset` y después `.venv/bin/python -m bot.main`
- El Mac tiene que tener tu sesión iniciada (vale con la pantalla bloqueada o en reposo).

### Pruebas sin enviar nada

```bash
.venv/bin/python -m bot.main --fecha 2026-11-24 --dry-run   # qué avisaría del BOE ese día
.venv/bin/python -m bot.main --probar-fuentes               # diagnóstico de boletines y webs
.venv/bin/python -m bot.main --probar-fuentes bopa bop-leon # solo algunas
.venv/bin/python -m bot.main --solo-fuentes --dry-run       # qué avisaría hoy de boletines y webs
.venv/bin/python -m pytest -q                                # tests
```

En GitHub, *Actions → Convocatorias → Run workflow* hace lo mismo (diagnóstico o simulación del BOE)
sin tocar tu Mac; ya no se ejecuta solo.

## Ajustes (`bot/config.py`)

| Ajuste | Para qué |
|---|---|
| `REGIONES` | Comunidades donde quieres cualquier plaza accesible |
| `GRUPOS_REGION` | `None` = todos los grupos. Para limitar: `["A1", "A2", "B", "C1"]` |
| `TITULACIONES` | Tus títulos (los usa la IA opcional) |
| `ANTHROPIC_API_KEY` (en `.env`) | Opcional: Claude revisa los casos "⚠️ revisa la titulación" |

## Cómo decide

- **Región**: por el departamento (comunidad autónoma), la provincia en el título
  (`Ayuntamiento de Siero (Asturias)`), capitales y universidades, y el boletín donde se publicaron
  las bases (BOPA, BOCYL, BOC, BOP de León…).
- **Informática**: palabras clave en cada plaza (informática, TIC, sistemas, analista,
  programador, ciberseguridad, telecomunicación…).
- **Titulación**: con grado + máster puedes ir a cualquier grupo salvo que se pida un título
  concreto. Las plazas de Arquitecto, Médico, Enfermería, Psicólogo, Trabajo Social, Derecho, etc. se
  descartan. A1/A2 de informática salen como ⚠️ porque algunas bases exigen Ingeniería Informática
  y hay que mirar si aceptan tu máster.
- **Plazo**: se calcula desde la fecha del BOE (los días hábiles excluyen sábados, domingos y
  festivos nacionales; los autonómicos y locales no, por eso es aproximado).

## Añadir o arreglar una fuente

Edita `fuentes.yaml` (cada fuente es una línea):

```yaml
- {id: ayto-mieres, nombre: Ayuntamiento de Mieres, tipo: web, region: Asturias, url: "https://www.mieres.es/"}
```

- Si el bot no llega al listado, pon la URL exacta de la página de empleo, o un `seguir` con el
  texto del enlace que lleva a ella: `seguir: "oferta de empleo|bolsas"`.
- Si la página cambia cada día, usa `{yyyy} {mm} {dd}` en la URL.
- `informatica: true` si todo lo que publica es de informática.

## Limitaciones conocidas

- La mayoría de URLs de `fuentes.yaml` están puestas por la portada oficial de cada boletín o
  entidad, sin verificar desde aquí. La primera ejecución de **probar_fuentes** dirá cuáles hay que
  ajustar; es normal que unas cuantas necesiten la URL exacta.
- Una misma convocatoria puede llegarte dos veces: desde su boletín provincial y, semanas después,
  desde el BOE.
- Los boletines que solo publican un PDF se leen por el sumario (primeras páginas); el detalle de la
  plaza hay que mirarlo en el PDF.
- La titulación exacta está en las bases: la etiqueta ⚠️ significa justo eso.

## Estructura

```
bot/
  fuentes/boe.py     lectura de la API del BOE
  fuentes/web.py     lector genérico de boletines y webs (RSS, HTML, PDF, CSV, XML)
fuentes.yaml         lista de boletines y webs
  clasificador.py    reglas: región, informática, grupo, titulación, plazo
  telegram.py        formato y envío
  store.py           SQLite: anuncios vistos y días procesados
  llm.py             afinado opcional con IA
  main.py            CLI (y modo --daemon por si algún día lo pones en un servidor)
tests/               tests con datos de ejemplo en el formato de la API
data/                estado en SQLite (lo actualiza el workflow)
.github/workflows/   pruebas manuales en GitHub Actions (diagnóstico y simulación)
scripts/mac/         instalación y tarea programada en el Mac (launchd)
```
