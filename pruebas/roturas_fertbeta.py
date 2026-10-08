#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Rompe el Programa de Fertilizacion (Beta) a proposito, una cosa por vez,
y comprueba que las pruebas lo noten. Una prueba que nunca falla no sirve
de nada; esto es lo que demuestra que sirven.

Cada rotura se aplica sobre una copia, se corren las revisiones y se
deja todo como estaba.

Uso:  python3 roturas_fertbeta.py
"""

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# (que se rompe, archivo, funcion que lo rompe, que prueba tiene que caer)
ROTURAS = [
    ("el redondeo del motor (Excel sube el 0,5)", "tecnico.html",
     lambda t: t.replace(
         "  return (y >= 0 ? Math.floor(y + 0.5) : Math.ceil(y - 0.5)) / f;",
         "  return (y >= 0 ? Math.floor(y) : Math.ceil(y)) / f;"),
     "funcional"),

    ("la primera fecha de la rejilla", "tecnico.html",
     lambda t: t.replace("  const d0 = fbMas(w8, -14);",
                         "  const d0 = fbMas(w8, -7);"),
     "funcional"),

    ("los complementarios suman al balance", "tecnico.html",
     lambda t: t.replace(
         "  for (let j = 0; j < FB_BASE; j++) {\n    const d = p.dosis[i + ',' + j];",
         "  for (let j = 0; j < FB_BASE; j++) {\n    const d = p.dosis[i + ',' + j] || p.dosisComp[i + ',' + j];"),
     "funcional"),

    ("el total por sector deja de multiplicar por la superficie", "tecnico.html",
     lambda t: t.replace("    sBase: tBase.map(v => fbRed(v * ha, 1)),",
                         "    sBase: tBase.map(v => fbRed(v, 1)),"),
     "funcional"),

    ("el factor de absorcion se toma siempre del cerezo", "tecnico.html",
     lambda t: t.replace(
         "  const col = p.especie === 'Cerezo' ? 'Cerezo' : p.especie === 'Kiwi' ? 'Kiwi' : 'Otras';",
         "  const col = 'Cerezo';"),
     "funcional"),

    ("el estado fenologico deja de juntar dos en la misma semana", "tecnico.html",
     lambda t: t.replace(
         "      if (i + 1 < ae.length && ae[i + 1].sem === sem) {",
         "      if (false) {"),
     "funcional"),

    ("la columna de complementarios vuelve a llamarse bc", "tecnico.html",
     lambda t: t.replace('<th class="fh-c">${fbEsc(p.comp[j])}',
                         '<th class="bc">${fbEsc(p.comp[j])}'),
     "verificar"),

    ("un estado fenologico con los dias al reves", "fertbeta.json",
     lambda t: t.replace('"dias": 205', '"dias": 5', 1),
     "verificar"),

    ("una ley fuera de rango en el catalogo", "fertbeta.json",
     lambda t: t.replace('"nombre": "Urea",\n   "tipo": "Base",\n   "categoria": "Nitrogenado",\n   "N": 46',
                         '"nombre": "Urea",\n   "tipo": "Base",\n   "categoria": "Nitrogenado",\n   "N": 460'),
     "verificar"),

    ("una fecha de inicio en el mes 13", "fertbeta.json",
     lambda t: t.replace('"Kiwi|Media": {\n   "dia": 22,\n   "mes": 9\n  }',
                         '"Kiwi|Media": {\n   "dia": 22,\n   "mes": 13\n  }'),
     "verificar"),
]


def correr(cual):
    """Devuelve True si la revision pasa, False si encuentra algo."""
    guion = "verificar.py" if cual == "verificar" else "funcional_fertbeta.py"
    r = subprocess.run([sys.executable, "-I", str(RAIZ / "pruebas" / guion)],
                       capture_output=True, text=True, timeout=700)
    return r.returncode == 0


def main():
    print("ROTURAS A PROPOSITO · Programa de Fertilizacion (Beta)")
    print("Cada linea rompe una cosa y comprueba que las pruebas la vean.\n")

    respaldo = Path(tempfile.mkdtemp(prefix="olo_roturas_"))
    for n in ("tecnico.html", "fertbeta.json"):
        shutil.copy2(RAIZ / n, respaldo / n)

    pilladas = escapadas = 0
    try:
        for titulo, archivo, romper, cual in ROTURAS:
            ruta = RAIZ / archivo
            sano = ruta.read_text(encoding="utf-8")
            roto = romper(sano)
            if roto == sano:
                print(f"  \033[33mSALTADA\033[0m {titulo}")
                print(f"          la rotura no encontro donde aplicarse en {archivo}")
                escapadas += 1
                continue
            ruta.write_text(roto, encoding="utf-8")
            try:
                paso = correr(cual)
            finally:
                ruta.write_text(sano, encoding="utf-8")
            if paso:
                escapadas += 1
                print(f"  \033[31mESCAPO \033[0m {titulo}  ({cual} no la vio)")
            else:
                pilladas += 1
                print(f"  \033[32mvista  \033[0m {titulo}  ({cual})")
    finally:
        for n in ("tecnico.html", "fertbeta.json"):
            shutil.copy2(respaldo / n, RAIZ / n)
        shutil.rmtree(respaldo, ignore_errors=True)

    print(f"\n{'-'*62}")
    if escapadas:
        print(f"\033[31m{escapadas} rotura(s) pasaron sin que nadie las viera.\033[0m")
        print("Falta una prueba que las cubra.")
        return 1
    print(f"\033[32mLas {pilladas} roturas fueron detectadas.\033[0m")
    return 0


if __name__ == "__main__":
    sys.exit(main())
