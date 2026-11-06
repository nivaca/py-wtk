# py-wtk: descripción del proyecto

*[Read in English](DESCRIPTION.md)*

## Qué es

py-wtk es un programa pequeño y libre para consultar el
[Wiktionary en inglés](https://en.wiktionary.org) sin abrir el navegador. Se le da una
palabra o una expresión de cualquier lengua y muestra la entrada completa del Wiktionary,
con un formato limpio, en la terminal o en una ventana de escritorio.

Está pensado para quienes consultan palabras a menudo: estudiantes y profesores de lenguas
(latín, griego, español, inglés…), traductores, filólogos y, en general, cualquiera que
quiera la información del Wiktionary sin el desorden ni la lentitud de la página web.

Lo hizo Nicolas Vaughan (<nivaca@fastmail.com>, <n.vaughan@uniandes.edu.co>) en 2026. Es
profesor asociado de Literatura de la Facultad de Artes y Humanidades de la Universidad de
los Andes, Bogotá, Colombia.

## Tres programas, un mismo núcleo

py-wtk viene en tres versiones, que comparten el mismo código por dentro y los mismos
ajustes:

| Programa     | Tipo                            | Para qué sirve                                  |
|--------------|---------------------------------|-------------------------------------------------|
| `py-wtk`     | línea de comandos               | consultas rápidas, guiones, salida en JSON para otros programas |
| `py-wtk-tui` | terminal a pantalla completa (curses) | leer entradas largas y pasar de una palabra a otra en la terminal |
| `py-wtk-gui` | ventana de escritorio (Tkinter) | el uso diario con el ratón, en modo claro u oscuro |

Como los tres programas convierten la entrada en texto con el mismo código, una entrada se
ve igual, y contiene lo mismo, en todos ellos.

## Qué muestra

No solo las definiciones, sino la entrada entera: etimología, pronunciación, definiciones
con ejemplos y citas fechadas, notas de uso, tablas de flexión (declinaciones y
conjugaciones, bien alineadas), sinónimos, términos derivados y relacionados,
descendientes, traducciones, referencias y lecturas adicionales.

Una página del Wiktionary suele tener muchas lenguas. py-wtk las muestra todas por
defecto, pero se pueden elegir solo las que interesan (`-l la`, o `-l la,es,it`), poner
algunas en primer lugar, mostrar solo ciertas secciones (`-o etymology`), ocultar otras o
pedir una vista breve con solo las definiciones.

## Funciones principales

- **Enlaces que funcionan.** Un enlace a otra entrada la abre en el programa, con todas
  las lenguas del filtro; los demás (Wikipedia, apéndices, otros diccionarios) se abren
  en el navegador. En la línea de comandos son hipervínculos de la terminal.
- **Búsqueda y sugerencias.** Se pueden buscar títulos de páginas; si una palabra no
  existe, se proponen otras parecidas. La ventana sugiere palabras mientras se escribe.
- **Navegación.** Índice por lenguas y secciones, búsqueda dentro de la página, historial
  con atrás y adelante, y, en la ventana, doble clic en cualquier palabra para buscarla.
- **Ajustes compartidos.** Un solo archivo `config.toml` para los tres programas, que se
  puede modificar desde la línea de comandos, desde una pantalla de ajustes en la
  interfaz de terminal, desde una ventana de ajustes en la interfaz gráfica o a mano.
- **Caché en disco.** Las páginas descargadas se guardan comprimidas durante un día
  (configurable), de modo que volver a consultar una palabra es instantáneo y no carga
  los servidores del Wiktionary.
- **Respetuoso con el Wiktionary.** Cuando el Wiktionary responde «Too Many Requests», el
  programa espera y vuelve a intentarlo por sí solo.
- **Salida para otros programas.** `py-wtk --json` da la entrada en JSON estructurado.

## Cómo está hecho

- **Python 3.11 o posterior, y nada más.** Solo se usa la biblioteca estándar (`urllib`,
  `html.parser`, `textwrap`, `curses`, `tkinter`, `tomllib`): no hay que instalar paquetes
  con pip. La ventana necesita Tkinter, que algunas distribuciones de Linux ofrecen en un
  paquete aparte.
- **Fuente de los datos.** Las páginas se descargan en HTML desde la API REST del
  Wiktionary y el propio programa las convierte en texto. En las entradas grandes cuyas
  traducciones están en una página aparte (como *house/translations*), esa página también
  se descarga y las traducciones se colocan en su sitio.
- **Organización.** El paquete `pywtk/` está dividido en capas: descarga y caché
  (`api.py`), análisis del HTML (`dom.py`), texto y colores (`text.py`), lenguas y
  secciones (`entry.py`), conversión de una entrada a texto o JSON (`render.py`), ajustes
  (`config.py`, `settings.py`), lo que comparten los tres programas (`common.py`) y un
  módulo para cada interfaz (`cli.py`, `tui.py`, `gui.py`, con `gui_theme.py` y
  `gui_fonts.py`). En total, unas 5000 líneas de Python.
- **Multiplataforma.** Funciona en Linux, macOS y Windows, y usa las carpetas habituales
  de ajustes y de caché de cada sistema.

## Distribución

- Un **AppImage** para Linux, que lleva su propio Python: se descarga, se hace ejecutable
  y se ejecuta.
- Un **zip** (o un clon del repositorio) para cualquier sistema con Python 3.11 o
  posterior, con tres lanzadores pequeños que se enlazan en el `PATH`.
- `py-wtk-install.py` añade los programas, con su icono, al menú de aplicaciones en Linux,
  al menú Inicio en Windows o a `~/Applications` en macOS, sin permisos de administrador.

Los guiones de `tools/` generan el zip y el AppImage, publican las versiones en GitHub y
Codeberg, toman las capturas de pantalla del README y vuelven a generar todos los iconos a
partir de un único SVG.

## Estado

La versión actual es la **1.6** (véanse en [NOTES.es.md](NOTES.es.md) los cambios de cada
versión). La interfaz de los programas está en inglés; la documentación, en inglés y en
español. Las versiones anteriores del proyecto se llamaban *py-wkt*; sus ajustes se
trasladan automáticamente.

## Licencia y créditos

py-wtk es software libre, bajo la [Licencia Pública General de GNU](LICENSE), versión 3 o
posterior. Copyright © 2026 Nicolas Vaughan.

El contenido de las entradas procede del Wiktionary y de sus colaboradores, bajo la
licencia [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/); py-wtk solo lo
muestra. py-wtk no es un proyecto oficial del Wiktionary ni de la Fundación Wikimedia.

Las instrucciones completas de instalación y de uso están en el [README](README.es.md).
