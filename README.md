# Bot de convocatorias de empleo público → Telegram

Revisa cada mañana (con GitHub Actions) y te avisa por Telegram de:

- **Asturias, Castilla y León y Cantabria**: cualquier plaza de acceso libre de cualquier organismo
  a la que puedas presentarte con tu grado + máster (también bolsas e interinidades).
- **Resto de España**: solo plazas de informática, también de cualquier organismo.

**Fuentes**

| Qué | Cómo |
|---|---|
| BOE, sección II.B | API oficial de datos abiertos (texto completo, cálculo de plazo) |
| 19 boletines autonómicos y 43 provinciales | lector genérico (`fuentes.yaml`) |
| Webs concretas: ayuntamientos, universidades, sanidad, empresas públicas, INCIBE, SEPI… | lector genérico (`fuentes.yaml`) |

El lector genérico entiende RSS, XML/CSV de datos abiertos, páginas HTML y el PDF del día de los
boletines que solo publican así. Desde la portada sigue hasta 2 niveles de enlaces tipo «sumario»,
«último boletín», «empleo», «procesos selectivos» o con la fecha de hoy, y se queda con los anuncios
de empleo. En la primera pasada de cada fuente manda **un único resumen** con lo que ya había
publicado; después, un mensaje por anuncio nuevo. Si una fuente falla 6 pasadas seguidas (~2 días),
te avisa una vez para que la revises.

Descarta lo que no abre plazo (listas de admitidos, tribunales, nombramientos, correcciones),
promoción interna, libre designación, concursos de traslados y plazas docentes (universidad y profesorado, que exigen doctorado o Máster de Profesorado).

Cada aviso del BOE trae organismo, plazas, grupo, sistema, etiqueta de titulación (✅ encaja /
⚠️ revisa), fin de plazo aproximado, dónde están las bases y el enlace. Los de boletines y webs
traen el título del anuncio, la etiqueta y el enlace.

## Puesta en marcha (GitHub Actions, sin servidor)

1. **Crea el bot de Telegram**: habla con `@BotFather` → `/newbot` → copia el token.
2. **Saca tu chat_id**: escribe cualquier cosa a tu bot y abre
   `https://api.telegram.org/bot<TOKEN>/getUpdates` → `"chat":{"id": ...}`.
   Si prefieres un canal, añade el bot como administrador y usa el id `-100…`.
3. **Sube este proyecto a un repo privado de GitHub** (por ejemplo `convocatorias-bot`).
4. En el repo: *Settings → Secrets and variables → Actions → New repository secret*:
   - `TELEGRAM_TOKEN`
   - `TELEGRAM_CHAT_ID`
   - `ANTHROPIC_API_KEY` (opcional)
5. **Comprueba las fuentes**: *Actions → Convocatorias → Run workflow* marcando **probar_fuentes**.
   En el resumen de la ejecución sale una tabla con cada boletín/web: si responde, cuántos anuncios
   de empleo encuentra y un ejemplo. Las marcadas con `*` tienen la URL sin verificar a mano; las que
   salgan en ❌ o ⚠️ se corrigen en `fuentes.yaml` (o se desactivan con `activa: false`).
   Después, *Run workflow* con **dry_run** y fecha `2026-11-24` para ver qué avisaría del BOE.
6. Lanza otra vez *Run workflow* sin *dry_run*: revisará los últimos 45 días y te avisará solo de las
   convocatorias que siguen con plazo abierto (las que ya cerraron se descartan).
   A partir de ahí se ejecuta solo de lunes a sábado (`.github/workflows/convocatorias.yml`).

El estado (anuncios ya vistos y días procesados) se guarda en `data/convocatorias.sqlite`, que el
propio workflow sube al repo tras cada pasada; así nunca se repite un aviso. Si el BOE aún no ha
salido o falla un envío a Telegram, la pasada siguiente lo reintenta.

Coste: cada ejecución tarda unos minutos (son ~110 fuentes); en un repo privado entra de sobra en los 2.000 minutos
gratuitos al mes de GitHub Actions.

### Probar en local

```bash
pip install -r requirements.txt pytest
python -m bot.main --fecha 2026-11-24 --dry-run   # qué avisaría del BOE, sin enviar nada
python -m bot.main --probar-fuentes                # diagnóstico de boletines y webs
python -m bot.main --probar-fuentes bopa bop-leon  # solo algunas
python -m bot.main --solo-fuentes --dry-run        # qué avisaría hoy de boletines y webs
TELEGRAM_TOKEN=... TELEGRAM_CHAT_ID=... python -m bot.main --prueba-telegram
python -m pytest -q
```

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
.github/workflows/   ejecución programada en GitHub Actions
```
