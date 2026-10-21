#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generador de miniaturas para transmisiones en vivo (YouTube / OBS).
Requisitos: pip install pillow   (tkinter viene con Python)
"""

import datetime as dt
import os
import tempfile
import time
import tkinter as tk
from itertools import combinations
from pathlib import Path
from tkinter import messagebox, ttk

from PIL import Image, ImageDraw, ImageFont

# ----------------------------------------------------------------------
# Configuración
# ----------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
CARPETA_FONDOS = BASE_DIR / "backgrounds"
CARPETA_FUENTES = BASE_DIR / "fonts"
CARPETA_SALIDA = BASE_DIR / "obs_output"
ARCHIVO_SALIDA = CARPETA_SALIDA / "miniatura_actual.png"

ANCHO, ALTO = 1280, 720
MARGEN_LATERAL = 90
MARGEN_SUPERIOR = 40
MARGEN_INFERIOR = 40

PREDICADOR_DEFECTO = "Inserte nombre predicador por defecto"
PREDICADORES = [PREDICADOR_DEFECTO, "Inserte nombre predicador 2"]

DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]
MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]

DISENOS = {
    "miercoles": {
        "fondo": CARPETA_FONDOS / "fondo_miercoles.png",
        "color": (20, 150, 75),     # verde
    },
    "domingo": {
        "fondo": CARPETA_FONDOS / "fondo_domingo.png",
        "color": (10, 85, 205),     # azul
    },
}

FUENTES_SANS = [
    "Montserrat-Medium.otf", "Montserrat-Regular.ttf",
    "arial.ttf", "Arial.ttf", "DejaVuSans.ttf", "LiberationSans-Regular.ttf",
]
FUENTES_SERIF = [
    "LibreBaskerville-VariableFont_wght.ttf",  # <-- Agrégalo aquí primero
    "LibreBaskerville-Regular.ttf", 
    "LibreBaskerville.ttf",
    "georgia.ttf", 
    "Georgia.ttf", 
    "times.ttf", 
    "DejaVuSerif.ttf",
    "LiberationSerif-Regular.ttf",
]

TAMANO_SANS = 40
ESPACIADO_SANS = 3          # px extra entre letras (tracking)


# ----------------------------------------------------------------------
# Fechas
# ----------------------------------------------------------------------
def formatear_fecha(hoy: dt.date) -> str:
    """Devuelve p. ej. 'Miércoles 14 de Octubre 2026'."""
    return f"{DIAS_SEMANA[hoy.weekday()]} {hoy.day} de {MESES[hoy.month - 1]} {hoy.year}"


# ----------------------------------------------------------------------
# Fuentes
# ----------------------------------------------------------------------
def cargar_fuente(candidatas, tamano):
    """Busca la primera fuente disponible (carpeta fuentes/ y luego sistema)."""
    for nombre in candidatas:
        for ruta in (CARPETA_FUENTES / nombre, nombre):
            try:
                return ImageFont.truetype(str(ruta), tamano)
            except OSError:
                continue
    # Último recurso: fuente integrada de Pillow (>= 10.1 acepta size)
    return ImageFont.load_default(size=tamano)


# ----------------------------------------------------------------------
# Fondo y degradado
# ----------------------------------------------------------------------
def cargar_fondo(ruta: Path) -> Image.Image:
    if not ruta.exists():
        raise FileNotFoundError(f"No se encontró la imagen de fondo:\n{ruta}")
    img = Image.open(ruta).convert("RGB")

    # Escalar para cubrir 1280x720 y recortar el centro
    escala = max(ANCHO / img.width, ALTO / img.height)
    nuevo = (round(img.width * escala), round(img.height * escala))
    img = img.resize(nuevo, Image.LANCZOS)
    izq = (nuevo[0] - ANCHO) // 2
    arr = (nuevo[1] - ALTO) // 2
    return img.crop((izq, arr, izq + ANCHO, arr + ALTO)).convert("RGBA")


def crear_degradado(color, centro=1, borde=0.20, curva=1) -> Image.Image:
    """
    Degradado espejo: más intenso en el centro vertical y
    desvaneciéndose hacia arriba y hacia abajo.
    """
    mitad = (ALTO - 1) / 2
    franja = Image.new("RGBA", (1, ALTO))
    pixeles = []
    for y in range(ALTO):
        cercania = 1 - abs(y - mitad) / mitad          # 1 centro, 0 bordes
        alfa = borde + (centro - borde) * (cercania ** curva)
        pixeles.append(color + (int(255 * alfa),))
    franja.putdata(pixeles)
    return franja.resize((ANCHO, ALTO), Image.BILINEAR)


# ----------------------------------------------------------------------
# Dibujo de texto
# ----------------------------------------------------------------------
def ancho_texto(draw, texto, fuente, espaciado=0):
    if espaciado == 0:
        return draw.textlength(texto, font=fuente)
    return sum(draw.textlength(c, font=fuente) for c in texto) + espaciado * (len(texto) - 1)


def _pintar(draw, texto, fuente, x, y, espaciado, color):
    if espaciado == 0:
        draw.text((x, y), texto, font=fuente, fill=color)
        return
    cx = x
    for c in texto:
        draw.text((cx, y), c, font=fuente, fill=color)
        cx += draw.textlength(c, font=fuente) + espaciado


def dibujar_texto(draw, texto, fuente, y_top, espaciado=0, sombra=2,
                  color=(255, 255, 255, 255)):
    """Dibuja una línea centrada horizontalmente con sombra suave."""
    ancho = ancho_texto(draw, texto, fuente, espaciado)
    x0 = (ANCHO - ancho) / 2
    if sombra:
        _pintar(draw, texto, fuente, x0 + sombra, y_top + sombra, espaciado, (0, 0, 0, 120))
    _pintar(draw, texto, fuente, x0, y_top, espaciado, color)


# ----------------------------------------------------------------------
# Título: tamaño y saltos de línea automáticos
# ----------------------------------------------------------------------
def mejor_particion(draw, palabras, fuente, n):
    """
    Parte las palabras en n líneas minimizando la línea más ancha
    (así las líneas quedan equilibradas, no 'APOCALIPSIS DE / HABACUC').
    """
    mejor = None
    for cortes in combinations(range(1, len(palabras)), n - 1):
        limites = (0,) + cortes + (len(palabras),)
        lineas = [" ".join(palabras[a:b]) for a, b in zip(limites, limites[1:])]
        peor = max(draw.textlength(l, font=fuente) for l in lineas)
        if mejor is None or peor < mejor[1]:
            mejor = (lineas, peor)
    return mejor


def ajustar_titulo(draw, texto, max_ancho, max_alto):
    """Busca el tamaño más grande que quepa dentro del área disponible."""
    lineas_manuales = None
    if "," in texto:
        lineas_manuales = [linea.strip().upper() for linea in texto.split(",") if linea.strip()]
    tamano_minimo = 16 if lineas_manuales is not None else 40
    palabras = texto.upper().split()
    for tam in range(190, tamano_minimo - 1, -2):
        fuente = cargar_fuente(FUENTES_SERIF, tam)
        asc, desc = fuente.getmetrics()
        lh = int((asc + desc) * 0.78)  # line height
        if lineas_manuales is not None:
            if (lh * len(lineas_manuales) <= max_alto
                    and all(draw.textlength(linea, font=fuente) <= max_ancho
                            for linea in lineas_manuales)):
                return fuente, lineas_manuales, lh
            continue
        for n in range(1, min(len(palabras), 5) + 1):
            res = mejor_particion(draw, palabras, fuente, n)
            if res and res[1] <= max_ancho and lh * n <= max_alto:
                return fuente, res[0], lh
    # Último recurso: tamaño mínimo sin cortes
    fuente = cargar_fuente(FUENTES_SERIF, tamano_minimo)
    asc, desc = fuente.getmetrics()
    lineas = lineas_manuales if lineas_manuales is not None else [texto.upper()]
    return fuente, lineas, int((asc + desc) * 0.78)


# ----------------------------------------------------------------------
# Generación
# ----------------------------------------------------------------------
def guardar_atomico(imagen: Image.Image) -> None:
    """
    Guarda primero en un archivo temporal y luego lo reemplaza.
    Así OBS nunca lee una imagen a medio escribir.
    """
    CARPETA_SALIDA.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".png", dir=CARPETA_SALIDA)
    os.close(fd)
    try:
        imagen.save(tmp, "PNG")
        for _ in range(10):
            try:
                os.replace(tmp, ARCHIVO_SALIDA)
                return
            except PermissionError:      # archivo bloqueado momentáneamente
                time.sleep(0.3)
        raise PermissionError(
            "No se pudo reemplazar miniatura_actual.png. "
            "¿Está abierto en otro programa?"
        )
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def generar_miniatura(titulo: str, predicador: str, clave_diseno: str) -> Path:
    diseno = DISENOS[clave_diseno]
    texto_fecha = formatear_fecha(dt.date.today())

    base = cargar_fondo(diseno["fondo"])
    degradado = crear_degradado(diseno["color"])
    lienzo = Image.alpha_composite(base, degradado)

    capa = Image.new("RGBA", lienzo.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(capa)

    # Fecha (arriba) y predicador (abajo)
    fuente_sans = cargar_fuente(FUENTES_SANS, TAMANO_SANS)
    asc, desc = fuente_sans.getmetrics()
    alto_sans = asc + desc
    dibujar_texto(draw, texto_fecha, fuente_sans, MARGEN_SUPERIOR, ESPACIADO_SANS)
    dibujar_texto(draw, predicador, fuente_sans,
                  ALTO - MARGEN_INFERIOR - alto_sans, ESPACIADO_SANS)

    # Título (centro)
    max_ancho = ANCHO - 2 * MARGEN_LATERAL
    zona_top = MARGEN_SUPERIOR + alto_sans + 10
    zona_bottom = ALTO - MARGEN_INFERIOR - alto_sans - 30
    max_alto = zona_bottom - zona_top

    fuente_titulo, lineas, lh = ajustar_titulo(draw, titulo, max_ancho, max_alto)
    y = zona_top + (max_alto - lh * len(lineas)) / 2
    for linea in lineas:
        dibujar_texto(draw, linea, fuente_titulo, y, espaciado=0, sombra=3)
        y += lh

    final = Image.alpha_composite(lienzo, capa).convert("RGB")
    guardar_atomico(final)
    return ARCHIVO_SALIDA


# ----------------------------------------------------------------------
# Interfaz gráfica
# ----------------------------------------------------------------------
class AppMiniatura(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Miniaturas")
        self.resizable(False, False)
        self.configure(padx=18, pady=16)

        hoy = dt.date.today()
        self.var_titulo = tk.StringVar()
        self.var_predicador = tk.StringVar(value=PREDICADOR_DEFECTO)
        self.var_diseno = tk.StringVar(value="Automático")

        ttk.Label(self, text="Título (separa líneas con comas):").grid(row=0, column=0, sticky="w")
        self.entry_titulo = ttk.Entry(self, textvariable=self.var_titulo, width=52)
        self.entry_titulo.grid(row=1, column=0, sticky="ew", pady=(2, 10))

        ttk.Label(self, text="Predicador:").grid(row=2, column=0, sticky="w")
        ttk.Combobox(self, textvariable=self.var_predicador,
                     values=PREDICADORES).grid(row=3, column=0, sticky="ew", pady=(2, 10))

        ttk.Label(self, text="Diseño:").grid(row=4, column=0, sticky="w")
        ttk.Combobox(self, textvariable=self.var_diseno, state="readonly",
                     values=["Automático", "Miércoles", "Domingo"]
                     ).grid(row=5, column=0, sticky="ew", pady=(2, 10))

        ttk.Label(self, text=f"Fecha detectada: {formatear_fecha(hoy)}",
                  foreground="#444").grid(row=6, column=0, sticky="w", pady=(0, 12))

        ttk.Button(self, text="Generar Miniatura", command=self.generar
                   ).grid(row=7, column=0, sticky="ew", ipady=6)

        self.lbl_estado = ttk.Label(self, text="", wraplength=440, foreground="gray")
        self.lbl_estado.grid(row=8, column=0, sticky="w", pady=(10, 0))

        self.entry_titulo.focus_set()
        self.bind("<Return>", lambda _e: self.generar())

    def _clave_diseno(self, hoy: dt.date) -> str:
        opcion = self.var_diseno.get()
        if opcion == "Miércoles":
            return "miercoles"
        if opcion == "Domingo":
            return "domingo"
        return "miercoles" if hoy.weekday() == 2 else "domingo"

    def generar(self):
        titulo = self.var_titulo.get().strip()
        predicador = self.var_predicador.get().strip()

        if not titulo or not any(linea.strip() for linea in titulo.split(",")):
            messagebox.showwarning("Falta el título", "Escribe el título de la predicación.")
            return
        if not predicador:
            messagebox.showwarning("Falta el predicador", "Escribe el nombre del predicador.")
            return

        hoy = dt.date.today()
        aviso = ""
        if self.var_diseno.get() == "Automático" and hoy.weekday() not in (2, 6):
            aviso = " (hoy no es miércoles ni domingo; se usó el diseño de Domingo)"

        try:
            ruta = generar_miniatura(titulo, predicador, self._clave_diseno(hoy))
        except Exception as e:
            messagebox.showerror("Error", str(e))
            return

        self.lbl_estado.config(text=f"✔ Miniatura generada: {ruta}{aviso}",
                               foreground="green")
        messagebox.showinfo("Listo",
                            f"La miniatura se generó correctamente en:\n{ruta}")


if __name__ == "__main__":
    AppMiniatura().mainloop()
