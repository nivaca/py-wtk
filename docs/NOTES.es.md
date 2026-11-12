# Notas de las versiones

## 1.8

**Un icono nuevo.** El `pW` entre corchetes del programa, dibujado ahora con formas en lugar
de con una fuente (así se ve igual en todos los sistemas), en blanco y crema sobre un fondo
verde azulado, con una marca de acento ámbar antes de la `p`, como en una pronunciación. Se
lee sobre paneles claros y oscuros, y hasta en 16 píxeles. Si añadiste el programa al menú
de aplicaciones con `py-wtk-install.py`, ejecútalo de nuevo para tener allí el icono nuevo.

## 1.7

**La ventana sigue la escala del escritorio en pantallas de alta resolución.** Con el
escritorio escalado (por ejemplo al 200 % en Plasma), la ventana del AppImage salía muy
pequeña: su Tk no hacía caso de la escala que el escritorio da a los programas X11
(`Xft.dpi`). Ahora la ventana la lee, y el texto y el tamaño de la ventana crecen con ella.

**Un paquete para Fedora.** py-wtk es ahora un RPM, que usa el Python y el Tk del sistema y
añade los tres programas al `PATH` y al menú de aplicaciones. Está en
[Copr](https://copr.fedorainfracloud.org/coprs/nivaca/py-wtk/), así que `dnf upgrade` trae
cada versión nueva (`sudo dnf copr enable nivaca/py-wtk && sudo dnf install py-wtk`), y las
versiones publicadas lo traen también, firmado, con su clave pública.

## 1.6

**Desinstalar quita solo lo que añadió el instalador.** `py-wtk-install.py --uninstall`
quita del menú de aplicaciones los archivos `.desktop` y los iconos que hizo el instalador,
y nada más: una entrada del mismo nombre que no escribió él (una sin el icono del programa)
se deja como está, y lo mismo los enlaces. `--only-gui` sigue la misma regla cuando quita
las entradas de la versión de terminal y de la línea de comandos.

**Error corregido: caracteres extraños en la línea de comandos.** Cuando una entrada larga
se abría en un paginador distinto de `less` (por ejemplo `PAGER=most`), sus enlaces
aparecían como caracteres extraños, del tipo `^[]8;;`. Solo `less` puede mostrar estos
enlaces, así que con cualquier otro paginador la entrada se muestra ahora sin ellos,
conservando sus colores. La captura de la línea de comandos del README también mostraba
estos caracteres; se ha tomado de nuevo.

## 1.5

**Los enlaces abren la entrada al principio.** Un enlace a otra entrada la abre ahora al
principio, con todas las lenguas del filtro (con `all`, todas las lenguas de la página),
en la ventana y en la interfaz de terminal. Antes saltaba a la lengua del enlace
(`rosa#Latin` bajaba hasta el latín), y parecía que la lengua había cambiado. Un enlace a
otra parte de la misma entrada sigue llevando allí.

## 1.4

**Error corregido.** `py-wtk --set NOMBRE=VALOR` y `py-wtk --unset NOMBRE` fallaban con
un error en lugar de cambiar el ajuste. Ahora funcionan de nuevo, y un nombre equivocado o
ambiguo (por ejemplo `--set links=false`, que es `cli.links` y `gui.links`) se indica con
claridad.

**Los mismos mensajes en los tres programas.** El tamaño de la caché en disco se muestra
igual en todas partes («2 pages, 192.7 KB»; la interfaz de terminal decía «1 pages»), y lo
mismo el mensaje de una lengua que la página no tiene. En la ventana, «Open in browser» y
«Clear disk cache» dicen ahora en la línea de estado lo que han hecho. En la línea de
comandos, un error de red al buscar (`-s`) da un mensaje claro.

**Instalador.** `py-wtk-install.py --only-gui` añade solo la ventana (`py-wtk (GUI)`) al menú
de aplicaciones; si una ejecución anterior añadió la versión de terminal y la línea de
comandos, sus entradas se quitan.

**Por dentro.** El código que cada uno de los tres programas tenía por su cuenta (el
historial de Atrás y Adelante, los enlaces, los mensajes, la caché en disco, las opciones
comunes) está ahora en un solo lugar, `pywtk/common.py`, y el dibujo de las listas y la
línea de comandos son más sencillos. Las entradas se muestran exactamente como antes.

**Para desarrolladores.** Los scripts que generan los paquetes están ahora en `tools/` con
los demás: `python3 tools/bundle-zip.py` y `python3 tools/bundle-appimage.py`. El nuevo
`tools/icons.py` genera de nuevo todos los iconos a partir de `icons/py-wtk.svg`.

## 1.3

**Nuevo icono.** El icono tiene ahora un fondo blanco, y las letras están mejor centradas.
Los iconos de todos los tamaños (Linux, macOS, Windows y los PNG) se han generado de nuevo a
partir de él. Vuelve a ejecutar `py-wtk-install.py` para tener el nuevo icono en el menú de
aplicaciones.

Las capturas de pantalla del README están actualizadas.

## 1.2

**Enlaces en los que se puede hacer clic.** Los enlaces de las entradas funcionan ahora en
los tres programas. Un enlace a otra entrada la abre en el programa, en la lengua del enlace
(`rosa#Latin` abre «rosa» en el latín); los demás enlaces (Wikipedia, los apéndices del
Wiktionary, otros diccionarios…) se abren en el navegador. Los enlaces a páginas que aún no
existen, las notas al pie y los enlaces de edición no son activos.

- **Ventana (`py-wtk-gui`):** los enlaces llevan el color de los enlaces y se subrayan al
  pasar el ratón; un clic los abre, y la barra de estado dice adónde llevan. Arrastrar
  sobre un enlace selecciona el texto sin abrirlo. Nuevo ajuste `gui.links` (activado por
  defecto).
- **Interfaz de terminal (`py-wtk-tui`):** los enlaces son azules (subrayados sin
  colores). Un clic los abre (con el ratón activado), y la nueva tecla `L` muestra la lista
  de los enlaces de la pantalla, para abrir uno con el teclado.
- **Línea de comandos (`py-wtk`):** los enlaces son hipervínculos (OSC 8), en los que se
  puede hacer clic en la mayoría de los terminales modernos y en `less`. Solo con colores,
  de modo que `--json`, `--no-color` y la salida hacia otros programas no cambian. Nuevo
  ajuste `cli.links` (activado por defecto), para desactivarlos en los terminales que los
  muestran como caracteres extraños.

El texto de las entradas es el mismo que antes.

**Línea de comandos interactiva.** `py-wtk -i` pide una palabra tras otra (cada línea
puede llevar también opciones, como `rosa -l la`; las opciones dadas junto a `-i` valen
para todas). `Ctrl-D` o `Ctrl-C` lo terminan.

**Instalador.** `py-wtk-install.py` añade también `py-wtk (CLI)` al menú de aplicaciones,
que abre `py-wtk -i` en un terminal. Las entradas están ahora solo en las categorías
Oficina y Diccionario, para que no aparezcan dos veces en algunos menús. Vuelve a
ejecutarlo para tener la nueva entrada.

**Otros cambios.** `py-wtk-tui`, iniciado sin terminal (por ejemplo, desde un menú cuyo
emulador de terminal falta), lo dice, en lugar de fallar con un error de curses.

## 1.0

Primera versión del nuevo py-wtk: la línea de comandos, la interfaz de terminal y la
ventana, con los ajustes compartidos entre ellos, la caché en disco, el zip y el AppImage, y
`py-wtk-install.py` para añadir los programas al menú de aplicaciones.
