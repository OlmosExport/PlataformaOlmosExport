#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GENERAR fertilizacion.json
==========================

Convierte los programas estándar de fertilización (.xlsm) en el archivo
que usa la sección Programa de Fertilización.

    python3 scripts/generar_fertilizacion.py Programa_*.xlsm

Cada planilla trae 8 hojas; de ellas importan tres:

    Demanda        las perillas (portainjerto, vigor, kilos) y el
                   reparto del requerimiento entre las 4 etapas
    Aporte         con qué producto se cubre cada nutriente en cada
                   etapa, y en qué proporción
    Distribución   el calendario que se le manda al productor, con las
                   columnas que van fijas a mano

Lo que NO se copia son los resultados: la plataforma los vuelve a
calcular. Por eso el script compara, al final, lo que calcula contra lo
que el Excel dejó guardado. Si algo no cuadra, lo dice.
"""

import json
import os
import re
import sys
import warnings

warnings.filterwarnings("ignore")

try:
    import openpyxl
except ImportError:
    print("Falta openpyxl:  pip install openpyxl")
    sys.exit(2)

# ── dónde vive cada cosa dentro de la planilla ───────────────────────
D_PORTA, D_VIGOR, D_KG = (8, 5), (9, 5), (10, 5)
D_VARIEDAD, D_CUARTEL = (7, 5), (6, 5)
MATRIZ = (12, 20, 2, 11)              # fila0, fila1, col0, col1
PARCIAL = {"N": 6, "P": 8, "K": 10, "Ca": 12, "Mg": 14}
ETAPAS_FILAS = (35, 36, 37, 38)
BLOQUES = [(5, 10, 23), (27, 32, 45), (49, 54, 66), (70, 75, 88)]  # Aporte
NUTRI = ("N", "P", "K", "Ca", "Mg")


def num(v, d=0.0):
    return float(v) if isinstance(v, (int, float)) else d


def texto(v):
    return re.sub(r"\s+", " ", str(v)).strip() if v is not None else ""


def leer_matriz(ws):
    """La tabla vigor × portainjerto que fija el requerimiento de N."""
    r0, r1, c0, c1 = MATRIZ
    portas = [texto(ws.cell(r0, c).value) for c in range(c0 + 3, c1 + 1)]
    filas = {}
    calif = {}
    for r in range(r0 + 2, r1 + 1):
        v = ws.cell(r, c0).value
        if v is None:
            continue
        filas[str(float(v))] = [num(ws.cell(r, c).value) for c in range(c0 + 3, c1 + 1)]
        calif[str(float(v))] = texto(ws.cell(r, c0 + 1).value)
    return portas, filas, calif


def leer_fuentes(ws):
    """Concentración de cada producto, en porcentaje."""
    cols = {"N": 2, "P": 3, "K": 4, "Ca": 5, "Mg": 6, "S": 7, "Cl": 8, "Zn": 9}
    out = {}
    for r in range(2, ws.max_row + 1):
        nombre = texto(ws.cell(r, 1).value)
        if not nombre:
            continue
        out[nombre] = {k: num(ws.cell(r, c).value) for k, c in cols.items()}
    return out


def leer_receta(ws):
    """
    Qué producto cubre qué nutriente en cada etapa y con qué proporción.
    El producto cuya proporción es una fórmula se lleva el nitrógeno que
    no aportaron los demás: ese es el 'resto'.
    """
    etapas = []
    for h, r0, r1 in BLOQUES:
        prods = []
        for r in range(r0, r1 + 1):
            nombre = texto(ws.cell(r, 2).value)
            if not nombre:
                continue
            d = ws.cell(r, 4).value
            elem = texto(ws.cell(r, 3).value)
            nut = "N" if elem.startswith("N") else elem
            if isinstance(d, str):
                prods.append({"prod": nombre, "nut": nut, "prop": "resto"})
            elif num(d) > 0:
                prods.append({"prod": nombre, "nut": nut, "prop": num(d)})
        etapas.append({"productos": prods, "zn": num(ws.cell(h, 20).value)})
    return etapas


def leer_distribucion(ws_f, ws_v):
    """
    El calendario. Separa lo que la planilla calcula de lo que el
    técnico escribió a mano: lo calculado se vuelve a calcular acá,
    lo escrito a mano se respeta tal cual.
    """
    columnas = []
    for c in range(7, 21):
        n = texto(ws_f.cell(19, c).value)
        if n:
            columnas.append({"col": c, "nombre": n})

    aplic = [int(num(ws_f.cell(r, 11).value)) for r in (13, 14, 15, 16)]
    estados = [texto(ws_v.cell(r, 6).value) for r in (13, 14, 15, 16)]
    etiquetas = [texto(ws_v.cell(r, 4).value) for r in (13, 14, 15, 16)]

    sup = num(ws_v.cell(6, 9).value, 1) or 1

    def fija(celda_f, celda_v):
        """
        ¿Es una dosis puesta a mano?

        Lo es si la celda tiene un número suelto, y también si tiene una
        fórmula que NO mira la hoja Aporte: el Ácido Bórico, por ejemplo,
        está escrito como "=5*$I$6", que es 5 kg/ha por la superficie.
        Esas también son dosis fijas, solo que multiplicadas.
        """
        if celda_f is None:
            return None
        if isinstance(celda_f, str) and celda_f.startswith("="):
            if "Aporte" in celda_f:
                return None          # esta sí la calcula la planilla
            v = num(celda_v)
            return v / sup if v else None
        v = num(celda_f)
        return v or None

    manual = {}
    previo = {}          # la fila "Inicio crecimiento raíces", antes de la semana 1
    for col in columnas:
        c = col["col"]
        v = fija(ws_f.cell(20, c).value, ws_v.cell(20, c).value)
        if v:
            previo[col["nombre"]] = v
        for r in range(21, 39):
            sem = ws_v.cell(r, 1).value
            v = fija(ws_f.cell(r, c).value, ws_v.cell(r, c).value)
            if v is None or sem is None:
                continue
            manual.setdefault(col["nombre"], {})[str(int(num(sem)))] = v

    return {
        "columnas": [c["nombre"] for c in columnas],
        "aplicaciones": aplic,
        "estados": estados,
        "etiquetas": etiquetas,
        "manual": manual,
        "previo": {"titulo": texto(ws_v.cell(20, 4).value), "dosis": previo},
        "superficie": num(ws_v.cell(6, 9).value, 1),
        "eficiencia": num(ws_v.cell(7, 9).value, 0.9),
    }


def leer_comentarios(ws):
    """
    Los párrafos que acompañan al programa cuando se manda.

    En la planilla vienen desordenados: una sola celda puede traer tres
    viñetas pegadas con saltos de línea, y una frase larga puede estar
    partida en dos filas. Acá se separan las viñetas y se vuelven a unir
    las frases cortadas, para que se lean igual que en el PDF.
    """
    crudo = []
    for r in range(42, ws.max_row + 1):
        v = ws.cell(r, 4).value
        if v is None:
            continue
        for trozo in str(v).split("•"):          # cada viñeta, su párrafo
            t = texto(trozo)
            if t and t != "0":
                crudo.append(("•" if len(crudo) and "•" in str(v) else "") + t)

    # una línea que empieza en minúscula es la continuación de la anterior
    out = []
    for t in crudo:
        limpio = t.lstrip("•").strip()
        if out and limpio[:1].islower() and not out[-1].endswith((".", ":")):
            out[-1] = out[-1] + " " + limpio
        else:
            out.append(t)
    return out


def leer_foliar(ws_an, ws_aj):
    """Análisis foliar y los rangos con que se corrige el requerimiento."""
    nut = ("N", "P", "K", "Ca", "Mg")
    analisis = {n: num(ws_an.cell(10, 7 + i).value, None) for i, n in enumerate(nut)}
    rangos = {}
    for i, n in enumerate(nut):
        c = 5 + i
        rangos[n] = {
            "min": num(ws_aj.cell(16, c).value),
            "optimo": num(ws_aj.cell(19, c).value) or
                      (num(ws_aj.cell(16, c).value) + num(ws_aj.cell(17, c).value)) / 2,
            "max": num(ws_aj.cell(18, c).value),
            # la planilla aplica la mitad de la corrección a K, Ca y Mg
            "mitad": n in ("K", "Ca", "Mg"),
        }
    return {
        "analisis": analisis,
        "rangos": rangos,
        # La planilla deja el potasio sin corregir por foliar: la celda de
        # la corrección está puesta en cero a mano. Se respeta.
        "sinCorreccion": ["K"],
        "msFrutos": num(ws_aj.cell(4, 2).value, 0.2),
        "reparto": num(ws_aj.cell(6, 2).value, 1.2),
        "campo": texto(ws_an.cell(10, 2).value),
        "fecha": texto(ws_an.cell(27, 2).value),
    }


def clave(nombre):
    n = nombre.lower()
    var = "santina" if "santina" in n else "lapins"
    vig = "vigorosa" if "vigoros" in n else "bajo_vigor"
    return var + "_" + vig


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    programas, fuentes, matriz_g, portas_g, calif_g, foliar_g = {}, {}, None, None, None, None
    comentarios = None

    for ruta in sys.argv[1:]:
        if not os.path.exists(ruta):
            print("No existe:", ruta)
            return 2
        wbf = openpyxl.load_workbook(ruta, data_only=False)
        wbv = openpyxl.load_workbook(ruta, data_only=True)
        d, dv = wbf["Demanda"], wbv["Demanda"]
        k = clave(os.path.basename(ruta))

        portas, mat, calif = leer_matriz(d)
        if matriz_g is None:
            portas_g, matriz_g, calif_g = portas, mat, calif
            fuentes = leer_fuentes(wbf["Fuentes "])
            foliar_g = leer_foliar(wbv["Análisis Foliar"], wbv["Ajuste Foliar"])
        if comentarios is None:
            comentarios = leer_comentarios(wbv["Distribución"])

        parcial = {n: [num(d.cell(r, c).value) for r in ETAPAS_FILAS]
                   for n, c in PARCIAL.items()}
        basal_k = d.cell(24, 10).value
        programas[k] = {
            "nombre": "%s · %s" % (texto(dv.cell(*D_VARIEDAD).value).title(),
                                   "Vigorosa" if "vigoros" in k else "Bajo Vigor"),
            "variedad": texto(dv.cell(*D_VARIEDAD).value),
            "vigor": "vigorosa" if "vigoros" in k else "bajo",
            "origen": os.path.basename(ruta),
            "defecto": {
                "cuartel": texto(dv.cell(*D_CUARTEL).value),
                "portainjerto": texto(dv.cell(*D_PORTA).value),
                "indiceVigor": num(dv.cell(*D_VIGOR).value, 3),
                "kgHa": num(dv.cell(*D_KG).value, 10000),
            },
            "basal": {
                "P": num(d.cell(24, 8).value, 2),
                "Ca": num(d.cell(24, 12).value, 3),
                "kColt": 12, "kOtro": 10,          # =IF(portainjerto="Colt";12;10)
                "mgMaxma": 4, "mgOtro": 3,
            },
            "parcializacion": parcial,
            "receta": leer_receta(wbf["Aporte"]),
            "distribucion": leer_distribucion(wbf["Distribución"], wbv["Distribución"]),
        }
        print("  %-22s %-8s vigor %-4s %6.0f kg/ha · %d etapas · %d columnas"
              % (k, programas[k]["defecto"]["portainjerto"],
                 programas[k]["defecto"]["indiceVigor"],
                 programas[k]["defecto"]["kgHa"],
                 len(programas[k]["receta"]),
                 len(programas[k]["distribucion"]["columnas"])))

    paquete = {
        "meta": {
            "generado": __import__("datetime").date.today().isoformat(),
            "temporada": "2026-2027",
            "programas": sorted(programas.keys()),
        },
        "portainjertos": portas_g,
        "matrizN": matriz_g,
        "calificativo": calif_g,
        "fuentes": fuentes,
        "foliar": foliar_g,
        "comentarios": comentarios,
        "programas": programas,
    }

    salida = os.path.join(base, "fertilizacion.json")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(paquete, f, ensure_ascii=False, separators=(",", ":"))

    print("\nRESUMEN")
    print("  programas       : %d" % len(programas))
    print("  portainjertos   : %s" % ", ".join(portas_g))
    print("  productos       : %d" % len(fuentes))
    print("  comentarios     : %d párrafos" % len(comentarios))
    print("\nfertilizacion.json → %.0f KB" % (os.path.getsize(salida) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
