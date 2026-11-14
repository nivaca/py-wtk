# py-wtk 1.12: descripción

*[Read in English](DESCRIPTION.md)*

## Análisis

py-wtk es un programa pequeño para consultar el Wiktionary en inglés (https://en.wiktionary.org) sin abrir el navegador. Se le da una palabra o una expresión de cualquier lengua y muestra la entrada completa del Wiktionary, con un formato limpio, en la terminal o en una ventana de escritorio. Las versiones anteriores se llamaban *py-wkt*. py-wtk es software libre, bajo la Licencia Pública General de GNU, versión 3 o posterior. El contenido de las entradas procede del Wiktionary y de sus colaboradores, bajo la licencia CC BY-SA 4.0; py-wtk solo lo muestra, y no es un proyecto oficial del Wiktionary ni de la Fundación Wikimedia.

Está pensado para quienes consultan palabras a menudo: estudiantes y profesores de lenguas (latín, griego, español, inglés…), traductores, filólogos y, en general, cualquiera que quiera la información del Wiktionary sin el desorden ni la lentitud de la página web. De ahí salieron los requisitos. Lo primero era mostrar la entrada entera, no solo las definiciones: etimología, pronunciación, definiciones con ejemplos y citas fechadas, notas de uso, tablas de flexión (declinaciones y conjugaciones, bien alineadas), sinónimos, términos derivados y relacionados, descendientes, traducciones, referencias y lecturas adicionales. Lo segundo, poder quedarse solo con lo que interesa: unas lenguas, unas secciones o una vista breve con solo las definiciones.

También tenía que servirle a cualquiera: desde la línea de comandos, para una consulta rápida o para otros programas; a pantalla completa en la terminal, para leer entradas largas, y en una ventana, para el uso diario con el ratón. Las tres formas debían mostrar lo mismo y compartir los ajustes, recordar la configuración de una sesión a otra y no depender de paquetes externos. Por último, el programa tenía que ser respetuoso con los servidores del Wiktionary: no volver a descargar una página que acaba de consultar y esperar cuando el Wiktionary pide que se esperen.

## Diseño

El programa está dividido en capas, cada una con un solo trabajo. `api.py` descarga las páginas, busca títulos y guarda la caché; `dom.py` lee el HTML en un árbol pequeño; `text.py` limpia el texto, mide el ancho de cada carácter en la terminal y pone los colores; `entry.py` reparte la página en lenguas y secciones y aplica los filtros y las opciones.

`render.py` convierte una entrada en texto o en JSON, y es el mismo para los tres programas, de modo que una entrada se ve igual, y contiene lo mismo, en todos ellos. `common.py` reúne lo demás que comparten: las opciones comunes, los mensajes, el historial de atrás y adelante, los enlaces y la caché en disco. La configuración vive en `settings.py`, que dice en un solo lugar qué es cada ajuste, su tipo y su valor por omisión, y en `config.py`, que lee y escribe el archivo.

Sobre esa base hay tres interfaces: la línea de comandos (`cli.py`, que se abre con `py-wtk`), la pantalla completa en la terminal (`tui.py`, con `py-wtk-tui`) y la ventana (`gui.py`, con `py-wtk-gui`), con su aspecto claro y oscuro (`gui_theme.py`) y sus fuentes (`gui_fonts.py`). `version.py` da el nombre, la versión, el commit del que se hizo el programa y el Python que necesita. Completan el conjunto tres lanzadores pequeños, un instalador de accesos en el menú del sistema (`py-wtk-install.py`) y los iconos.

No hay datos propios: las páginas se descargan en HTML desde la API REST del Wiktionary (`/api/rest_v1/page/html/…`). Las páginas descargadas se guardan comprimidas en la carpeta de caché habitual de cada sistema durante un día (ajuste `general.cache_days`), de modo que volver a consultar una palabra es instantáneo. La configuración del usuario queda en un archivo TOML legible, `config.toml`, en la carpeta de configuración habitual de cada sistema.

## Implementación

Está escrito en Python 3.15 o superior y usa solo la biblioteca estándar, sin paquetes externos: `urllib`, `html.parser`, `textwrap`, `curses`, `tkinter` y `tomllib`. El paquete `pywtk/` tiene 16 módulos, unas 5200 líneas. Aprovecha lo que ofrece el Python actual: anotaciones de tipos, clases genéricas, f-strings y `tomllib` para leer la configuración.

La línea de comandos usa `argparse`. Escribe la entrada con colores, la pasa a un paginador cuando es larga y tiene un modo interactivo (`-i`) que pide una palabra tras otra; con `--json` da la entrada en JSON estructurado. La pantalla completa para la terminal usa `curses`, y la ventana, Tkinter. Las dos tienen un índice por lenguas y secciones, búsqueda dentro de la página, historial con atrás y adelante, recarga y una pantalla o ventana de ajustes con todas las opciones. En la ventana, además, se sugieren palabras mientras se escribe y un doble clic en cualquier palabra la busca. Si una palabra no existe, se proponen otras parecidas.

Los tres programas comparten el archivo `config.toml`, que se puede modificar desde la línea de comandos (`--set`, `--unset`), desde los ajustes de la terminal o de la ventana, o a mano. Cada programa escribe solo los ajustes que se cambian, sobre el archivo tal como está en ese momento, así que si la ventana y la terminal están abiertas a la vez, una no deshace los cambios de la otra. Los ajustes de las versiones llamadas *py-wkt* (su `config.toml` o su `settings.ini`, más antiguo) pasan una sola vez a la nueva carpeta, y el archivo viejo se renombra `*.old`.

Cuando el Wiktionary responde «Too Many Requests» o está ocupado un momento, el programa espera (lo que diga la respuesta, si lo dice) y vuelve a intentarlo por sí solo. Las entradas grandes cuyas traducciones están en una página aparte (como *house/translations*) descargan también esa página, y las traducciones se colocan en su sitio.

### Enlaces

Desde la versión 1.2, los enlaces de una entrada funcionan en los tres programas. Un enlace a otra entrada la abre en el programa, arriba y con todas las lenguas del filtro; los demás (Wikipedia, los apéndices del Wiktionary, otros diccionarios) se abren en el navegador. Los enlaces a páginas que todavía no existen, las notas al pie y los enlaces de edición no se pueden pulsar.

En la ventana, los enlaces tienen el color de los enlaces y se subrayan bajo el puntero; arrastrar sobre uno selecciona el texto sin abrirlo. En la terminal son azules, un clic los abre y la tecla `L` los lista para abrir uno con el teclado. En la línea de comandos son hipervínculos de la terminal (OSC 8), que la mayoría de las terminales modernas y `less` permiten pulsar; solo se escriben con colores, así que `--json`, `--no-color` y la salida hacia otros programas no cambian. Como solo `less` sabe mostrarlos, con cualquier otro paginador (por ejemplo `PAGER=most`) la entrada se muestra sin ellos, con sus colores.

### Proceso y distribución

El trabajo pasó por seis etapas: la conversión del HTML del Wiktionary en texto, con sus lenguas, secciones y tablas; los tres programas sobre un mismo código de presentación; los ajustes compartidos y la caché; los enlaces; la distribución (zip, AppImage e instalador), y, por último, la reunión en `common.py` de lo que cada programa tenía por su cuenta.

El programa se distribuye como un zip (o un clon del repositorio) para cualquier sistema con Python 3.15 o posterior, con tres lanzadores que se enlazan en el `PATH`, como un AppImage para Linux, que lleva su propio Python, y, desde la 1.7, como un paquete RPM para Fedora, en Copr y, firmado, con cada versión publicada, que usa el Python y el Tk del sistema y pone los tres programas en el `PATH` y en el menú de aplicaciones. El Tk del AppImage es más antiguo (8.6) y no hace caso de la escala que el escritorio da a los programas X11 (`Xft.dpi`), así que en una pantalla de alta resolución escalada su ventana salía muy pequeña; desde la 1.7 la ventana lee esa escala por su cuenta. La 1.10 salió también como Flatpak, para cualquier Linux (el Python de su runtime no trae Tk, así que Tcl/Tk y el `_tkinter` de Python se compilaban dentro de él), al que se renunció después. El zip y el AppImage llevan el commit del que se hicieron, que muestran `--version` y *About*. Los guiones de `tools/` generan el zip y el AppImage, publican las versiones, toman las capturas de pantalla del README y vuelven a generar todos los iconos a partir de un único SVG (desde la 1.8, el `pW` entre corchetes, dibujado con formas y no con una fuente, sobre un fondo verde azulado).

El código se gestiona con git, en un solo repositorio publicado en GitHub y en Codeberg. `tools/release.py` publica cada versión en los dos sitios, con el zip, el AppImage y el RPM firmado, que `packaging/` genera y que se envía también a Copr.

## Validación

El programa se probó con Python 3.15, la versión mínima, en Linux. `tools/screenshots.py` maneja los tres programas como lo haría un usuario (la ventana en modo claro y oscuro), con ajustes y caché propios, para no tocar los del usuario; de ahí salen las capturas del README, que se revisaron a ojo y se volvieron a tomar en la 1.6. Con un Python demasiado viejo, el programa da un mensaje claro en lugar de un error. Todavía no tiene pruebas automáticas.

## Plataforma

Funciona en Linux, Windows y macOS, y usa las carpetas habituales de ajustes y de caché de cada sistema. Necesita Python 3.15 o superior; para la ventana hace falta Tkinter, que viene en los instaladores de python.org y que en algunas distribuciones de Linux es un paquete aparte, como `python3-tkinter` o `python3-tk`. El AppImage para Linux no necesita nada más.

Necesita conexión a internet para descargar las páginas, aunque las que ya están en la caché se muestran sin volver a pedirlas.

## Ambiente

Lo desarrollé en Fedora Linux 45 con KDE Plasma, con Python 3.15, y con git, con repositorios en GitHub y Codeberg.

Para usarlo no hay que instalar nada: se descarga el AppImage y se ejecuta, o se descomprime el zip y se ejecutan sus lanzadores (`py-wtk`, `py-wtk-tui`, `py-wtk-gui`). Si se quiere, `python3 py-wtk-install.py` añade accesos al menú de aplicaciones, con su icono y sin permisos de administrador. Los ajustes quedan en la carpeta de configuración del usuario (`~/.config/py-wtk/config.toml` en Linux) y la caché en su carpeta de caché (`~/.cache/py-wtk` en Linux).

Las instrucciones completas de instalación y de uso están en el [README](../README.es.md); los cambios de cada versión, en [NOTES.es.md](NOTES.es.md).
