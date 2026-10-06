#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
GENERAR precios.json
====================

Convierte la planilla de precios de proveedores en el archivo que usa la
sección Precios de Agroquímicos.

    python3 scripts/generar_precios.py PRECIOS_PROVEEDORES.xlsx

QUÉ HACE DISTINTO A LA PLANILLA
-------------------------------
La planilla trae dos columnas calculadas, "MEJOR PRECIO" y "PROVEEDOR
ÓPTIMO", que están rotas: hay celdas con #REF! y muchas filas donde el
mejor precio no es el menor de la fila. Acá esas dos columnas se ignoran
y se vuelven a calcular:

    1. se toman los precios de los proveedores
    2. se descartan los vacíos, los textos y los ceros
    3. el menor que quede es el mejor precio
    4. si no queda ninguno, el producto va "sin precio"

Al final el script informa cuántas filas de la planilla estaban mal, para
que se puedan corregir allá también.

LA CATEGORÍA
------------
La planilla no tiene columna de categoría. Se deduce de datos que ya
existen en la plataforma, no se inventa:

    · del programa fitosanitario, que trae el objetivo de cada producto
      ("Arañitas" → acaricida, "Botritis" → fungicida, …)
    · de la lista de fuentes del programa de fertilización, que son los
      fertilizantes

Lo que no calza con ninguno de los dos queda en "Otros", para
reclasificarlo a mano cuando se quiera.
"""

import json
import os
import re
import sys
import unicodedata
import warnings

warnings.filterwarnings("ignore")

try:
    import openpyxl
except ImportError:
    print("Falta openpyxl:  pip install openpyxl")
    sys.exit(2)

# ── el objetivo que viene en el programa decide la categoría ──────────
REGLAS = [
    ("Acaricida",    r"arañit|acaro|ácaro|bimaculad|arañas"),
    ("Fungicida",    r"botrit|monili|alternar|oidio|cancer|cáncer|cytospora|"
                     r"pudric|tizon|tizón|venturia|fungic|bacterial|penicilium|"
                     r"enfermedades de madera"),
    ("Insecticida",  r"escama|polilla|trips|thrips|chanchito|burrito|drosoph|"
                     r"pulgon|pulgón|insect|huevos de|conchuela"),
    ("Herbicida",    r"maleza|herbicid"),
    ("Regulador",    r"cuaja|division celular|división celular|giberel|giberél|"
                     r"control de vigor|firmeza y calibre|floracion|floración|"
                     r"caída de|caida de|receso|adelantar|concentrar"),
    ("Bioestimulante", r"estrés|estres|resistencia planta|carbohidrat|color|"
                     r"calibre|cracking|osmoprotector|antioxidante|reservas|"
                     r"metabolismo|tubo polinico|tubo polínico|golpe de sol|"
                     r"bloqueador solar|brix|pasma"),
    ("Nutriente",    r"nutrient|acumular reservas|traslocacion|traslocación"),
]

CAT_ORDEN = ["Fungicida", "Acaricida", "Insecticida", "Herbicida", "Regulador",
             "Bioestimulante", "Nutriente", "Coadyuvante", "Otros"]

COADYUVANTES = r"silwet|silwett|aceite mineral|aceite pure|humectante|mojante|adherente"

# El ingrediente activo dice a qué familia pertenece el producto. Es la
# misma lectura que haría un agrónomo mirando la etiqueta.
POR_INGREDIENTE = [
    ("Acaricida",    r"abamectin|etoxazol|bifenazato|spirodiclofen|clofentezin|"
                     r"hexitiazox|fenpiroximato|acequinocil|cyflumetofen"),
    ("Fungicida",    r"cobre|cuprico|cúprico|azufre|captan|dodina|tebuconazol|"
                     r"difenoconazol|azoxistrobin|azoxystrobin|fludioxonil|"
                     r"fenhexamid|fenbuconazol|pyraclostrobin|boscalid|"
                     r"ciprodinil|iprodion|mancozeb|metalaxil|penconazol|"
                     r"trifloxistrobin|fluopyram|bacillus subtilis|estreptomicin|"
                     r"gentamicin|oxitetraciclin|caldo bordal|piraclostrobin"),
    ("Insecticida",  r"acetamiprid|imidacloprid|spinosad|spinetoram|indoxacarb|"
                     r"clorantranilipro|ciantranilipro|spirotetramat|diazinon|"
                     r"lambda|cipermetrin|bifentrin|piriproxifen|buprofezin|"
                     r"metoxifenocida|tiametoxam|novaluron|clorpirifos"),
    ("Regulador",    r"giberel|giberél|prohexadiona|aviglicin|cianamida|"
                     r"etefon|ethephon|naftiloxiac|cloruro de mepiquat|cppu|"
                     r"forclorfenuron|citoquinin|auxina"),
    ("Nutriente",    r"\bboro\b|\bzinc\b|\bcalcio\b|\bmagnesio\b|\bpotasio\b|"
                     r"\bmolibdeno\b|nitrato de|sulfato de magnesio|sulfato de potasio|"
                     r"fosfato|urea\b|acido borico|ácido bórico"),
    ("Bioestimulante", r"ascophillum|ascophyllum|ecklonia|alga|aminoacid|"
                     r"aa;|glicina betaina|quitosano|acido salicilico|"
                     r"extracto|humic|fulvic|oxido de silicio|óxido de silicio|"
                     r"prolina|manitol|caolin|vit b"),
]


def quitar(s):
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn").lower()


# sufijos de formulación: "80 WP", "430 SC", "25 EW"… El mismo producto
# aparece con varias concentraciones y hay que reconocerlo igual.
FORMULACION = (r"\b\d+([.,]\d+)?\s*"
               r"(wp|wg|sc|ec|ew|sl|sp|se|cs|od|fs|me|df|dc|sg|ad|wst|f|l|g)\b")


def claves(s):
    """Todos los nombres con que puede aparecer un producto."""
    bruto = quitar(s)
    partes = re.split(r"\s+o\s+|\s*/\s*|\s*,\s*", bruto)
    out = []
    for p in partes:
        k = clave(p)
        if k and k not in out:
            out.append(k)
    return out or [clave(s)]


def clave(s):
    """
    Nombre reducido a lo comparable: sin tildes, sin signos, sin la
    formulación del final. Así "Captan 80 WP" y "Captan 83 WP" se
    reconocen como el mismo producto.
    """
    t = quitar(s)
    t = re.split(r"\s+o\s+|\s*/\s*|\s*,\s*|\s+\(", t)[0]   # "Amistar Top ó Tatio" → "amistar top"
    t = re.sub(r"\bmg\b", "magnesio", t)
    t = re.sub(r"\bca\b", "calcio", t)
    t = re.sub(r"\bk\b", "potasio", t)
    t = re.sub(r"[^a-z0-9 ]", " ", t)
    t = re.sub(FORMULACION, " ", t)
    t = re.sub(r"\s+\d+([.,]\d+)?\s*$", " ", t)              # un número suelto al final
    t = re.sub(r"\s+", " ", t).strip()
    return t


def categoria(nombre, objetivo, ingrediente, fertilizantes):
    n = quitar(nombre)
    if re.search(COADYUVANTES, n):
        return "Coadyuvante"
    k = clave(nombre)
    for f in fertilizantes:
        if k == f or k.startswith(f) or f.startswith(k):
            return "Nutriente"
    o = quitar(objetivo)
    for cat, patron in REGLAS:
        if o and re.search(patron, o):
            return cat
    i = quitar(ingrediente)
    for cat, patron in POR_INGREDIENTE:
        if i and re.search(patron, i):
            return cat
    return "Otros"


def busca(k, mapa):
    """Calce exacto y, si no, por prefijo de al menos 6 letras."""
    if not k:
        return None
    if k in mapa:
        return mapa[k]
    for otro, v in mapa.items():
        if len(k) >= 6 and len(otro) >= 6 and (k.startswith(otro) or otro.startswith(k)):
            return v
    return None


def cargar_programa(ruta_html):
    """Productos del programa fitosanitario: nombre → ingrediente y objetivo."""
    if not os.path.exists(ruta_html):
        return {}
    s = open(ruta_html, encoding="utf-8").read()
    m = re.search(r"var FITO_CEREZO=(\[.*?\]);var FITO_ALT=", s, re.S)
    if not m:
        return {}
    out = {}
    por_ing = {}
    for r in json.loads(m.group(1)):
        # cada fila con "ap" abre una aplicación nueva; las de abajo
        # son productos de esa misma aplicación y comparten su objetivo
        if not r.get("prod"):
            continue
        ks = claves(re.sub(r"\s*\d+$", "", r["prod"]))
        if not ks:
            continue
        a = out.setdefault(ks[0], {"ing": "", "obj": []})
        for extra in ks[1:]:
            out.setdefault(extra, a)
        if r.get("ing") and not a["ing"]:
            a["ing"] = re.sub(r"\s+", " ", r["ing"]).strip()
        o = re.sub(r"\s+", " ", str(r.get("obj") or "")).strip()
        if o and o not in a["obj"]:
            a["obj"].append(o)
        if a["ing"]:
            por_ing.setdefault(clave(a["ing"]), a)

    # la tabla de alternativas empareja cada producto del programa con sus
    # equivalentes: el equivalente hereda lo que se sabe del original
    ma = re.search(r"var FITO_ALT=(\[.*?\]);", s, re.S)
    if ma:
        actual = None
        for r in json.loads(ma.group(1)):
            if r.get("prog"):
                actual = busca(clave(r["prog"]), out)
            if r.get("alt") and actual:
                k = clave(r["alt"])
                if k and k not in out:
                    out[k] = {"ing": actual.get("ing", ""), "obj": list(actual.get("obj", []))}

    # el ingrediente activo también sirve para reconocer: "Acido Giberélico"
    # como producto calza con el ingrediente del Proggib
    for k, v in por_ing.items():
        out.setdefault(k, v)
    return out


def cargar_fertilizantes(ruta_json):
    if not os.path.exists(ruta_json):
        return set()
    d = json.load(open(ruta_json, encoding="utf-8"))
    return {clave(p) for p in (d.get("fuentes") or {})}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    ruta = sys.argv[1]
    if not os.path.exists(ruta):
        print("No existe:", ruta)
        return 2

    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    programa = cargar_programa(os.path.join(base, "tecnico.html"))
    fertilizantes = cargar_fertilizantes(os.path.join(base, "fertilizacion.json"))
    print("Referencias: %d productos del programa · %d fertilizantes\n"
          % (len(programa), len(fertilizantes)))

    ws = openpyxl.load_workbook(ruta, data_only=True)[openpyxl.load_workbook(ruta).sheetnames[0]]
    proveedores = []
    for c in range(2, ws.max_column + 1):
        n = ws.cell(1, c).value
        if not n or re.search(r"mejor precio|optimo|óptimo", str(n), re.I):
            continue
        proveedores.append({"col": c, "nombre": re.sub(r"\s+", " ", str(n)).strip().title()})

    productos, mal_excel, sin_precio, sin_cat = [], 0, 0, 0
    for r in range(2, ws.max_row + 1):
        nombre = ws.cell(r, 1).value
        if not nombre or not str(nombre).strip():
            continue
        nombre = re.sub(r"\s+", " ", str(nombre)).strip()

        precios = {}
        for p in proveedores:
            v = ws.cell(r, p["col"]).value
            if isinstance(v, (int, float)) and v > 0:
                precios[p["nombre"]] = round(float(v), 2)

        mejor, prov = None, None
        if precios:
            prov = min(precios, key=lambda k: precios[k])
            mejor = precios[prov]
        else:
            sin_precio += 1

        # ¿la planilla tenía bien su propio cálculo?
        jv = ws.cell(r, 10).value
        if mejor is not None and isinstance(jv, (int, float)) and abs(jv - mejor) > 0.01:
            mal_excel += 1

        ref = busca(clave(nombre), programa) or {}
        cat = categoria(nombre, " ".join(ref.get("obj", [])),
                        ref.get("ing", "") or nombre, fertilizantes)
        if cat == "Otros":
            sin_cat += 1

        productos.append({
            "nombre": nombre,
            "cat": cat,
            "ing": ref.get("ing", ""),
            "obj": ref.get("obj", [])[:3],
            "precios": precios,
            "mejor": mejor,
            "prov": prov,
        })

    # ── juntar los nombres repetidos ───────────────────────────────
    # La planilla trae el mismo producto en dos o tres filas. Para comparar
    # precios eso estorba: se juntan en uno solo y se deja, por proveedor,
    # el precio más bajo de las filas repetidas.
    por_nombre, repetidos = {}, 0
    for p in productos:
        k = quitar(p["nombre"])
        if k in por_nombre:
            repetidos += 1
            q = por_nombre[k]
            for prov, v in p["precios"].items():
                if prov not in q["precios"] or v < q["precios"][prov]:
                    q["precios"][prov] = v
            if not q["ing"] and p["ing"]:
                q["ing"] = p["ing"]
            if q["cat"] == "Otros" and p["cat"] != "Otros":
                q["cat"] = p["cat"]
            q["repetido"] = q.get("repetido", 1) + 1
        else:
            por_nombre[k] = p
    productos = list(por_nombre.values())
    for p in productos:
        if p["precios"]:
            p["prov"] = min(p["precios"], key=lambda k: p["precios"][k])
            p["mejor"] = p["precios"][p["prov"]]

    # ── precios que no se parecen a los demás ──────────────────────
    # Un proveedor veinte veces más caro que el más barato suele ser un
    # error de unidad o un cero de más. No se corrige: se marca.
    raros = 0
    for p in productos:
        v = list(p["precios"].values())
        if len(v) > 1 and max(v) > min(v) * 20:
            p["sospechoso"] = True
            raros += 1

    productos.sort(key=lambda p: (CAT_ORDEN.index(p["cat"]), quitar(p["nombre"])))
    conteo = {}
    for p in productos:
        conteo[p["cat"]] = conteo.get(p["cat"], 0) + 1

    paquete = {
        "meta": {
            "generado": __import__("datetime").date.today().isoformat(),
            "origen": os.path.basename(ruta),
            "moneda": "USD",
            "unidad": "kg o L",
            "productos": len(productos),
            "corregidos": mal_excel,
            "repetidos": repetidos,
            "sospechosos": raros,
        },
        "proveedores": [p["nombre"] for p in proveedores],
        "categorias": [c for c in CAT_ORDEN if conteo.get(c)],
        "conteo": conteo,
        "productos": productos,
    }
    salida = os.path.join(base, "precios.json")
    with open(salida, "w", encoding="utf-8") as f:
        json.dump(paquete, f, ensure_ascii=False, separators=(",", ":"))

    for c in paquete["categorias"]:
        print("  %-16s %3d productos" % (c, conteo[c]))
    print("\nRESUMEN")
    print("  productos           : %d" % len(productos))
    print("  proveedores         : %s" % ", ".join(paquete["proveedores"]))
    print("  sin ningún precio   : %d" % sin_precio)
    print("  sin categoría       : %d (quedaron en 'Otros')" % sin_cat)
    print("\nREVISAR EN LA PLANILLA")
    print("  · en %d filas el 'MEJOR PRECIO' no era el menor de la fila" % mal_excel)
    print("  · %d filas repetían un producto ya listado; se juntaron en una" % repetidos)
    print("  · %d productos tienen un proveedor 20 veces más caro que el más" % raros)
    print("    barato: suele ser un error de unidad. Quedan marcados en la página.")
    print("\nprecios.json → %.0f KB" % (os.path.getsize(salida) / 1024))
    return 0


if __name__ == "__main__":
    sys.exit(main())
