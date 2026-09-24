#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VERIFICACIÓN DE LA PLATAFORMA · Exportadora Los Olmos
=====================================================

Revisa los archivos del sitio sin abrir un navegador. Corre en segundos
y no necesita instalar nada más que Python y Node.

    python3 pruebas/verificar.py

Devuelve 0 si todo está bien y 1 si hay algún error, para que GitHub
Actions pueda detener una publicación con problemas.

Cada revisión está acá porque alguna vez algo se rompió por eso.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGINAS = ["index.html", "clima.html", "tecnica.html"]
JSONS = ["datos.json", "config.json", "cuarteles.json",
         "heladas_comunas.json", "manifest.webmanifest"]
OBLIGATORIOS = PAGINAS + JSONS + ["sw.js", "icon-192.png", "icon-512.png",
                                  "apple-touch-icon.png", "LEEME.txt"]

errores = []
avisos = []


def error(seccion, msg):
    errores.append((seccion, msg))


def aviso(seccion, msg):
    avisos.append((seccion, msg))


def leer(nombre):
    with open(os.path.join(RAIZ, nombre), encoding="utf-8") as f:
        return f.read()


def scripts_de(html):
    """Devuelve el JavaScript embebido de una página, sin los <script src>."""
    return re.findall(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", html, re.S)


# ─────────────────────────────────────────────────────────────
def r_archivos():
    """Que no falte ninguno de los archivos del sitio."""
    faltan = [f for f in OBLIGATORIOS
              if not os.path.exists(os.path.join(RAIZ, f))]
    if faltan:
        error("archivos", "faltan en la carpeta: " + ", ".join(faltan))


def r_json():
    """Que todos los JSON se puedan leer."""
    for n in JSONS:
        ruta = os.path.join(RAIZ, n)
        if not os.path.exists(ruta):
            continue
        try:
            json.load(open(ruta, encoding="utf-8"))
        except Exception as e:
            error("json", "%s no se puede leer: %s" % (n, e))


def r_sintaxis():
    """Que el JavaScript de cada página no tenga errores de sintaxis.

    Es la revisión que más veces habría evitado una página en blanco.
    """
    if not _hay_node():
        aviso("sintaxis", "Node no está instalado, no se revisó el JavaScript")
        return
    for n in PAGINAS + ["sw.js"]:
        ruta = os.path.join(RAIZ, n)
        if not os.path.exists(ruta):
            continue
        codigo = leer(n) if n.endswith(".js") else "\n;\n".join(scripts_de(leer(n)))
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                         encoding="utf-8") as tmp:
            tmp.write(codigo)
            tmp_path = tmp.name
        try:
            p = subprocess.run(["node", "--check", tmp_path],
                               capture_output=True, text=True)
            if p.returncode != 0:
                detalle = (p.stderr or "").strip().splitlines()
                pista = detalle[min(2, len(detalle) - 1)] if detalle else ""
                error("sintaxis", "%s tiene un error de JavaScript: %s" % (n, pista))
        finally:
            os.unlink(tmp_path)


def _hay_node():
    try:
        subprocess.run(["node", "--version"], capture_output=True)
        return True
    except FileNotFoundError:
        return False


def r_secretos():
    """Que no se publique ninguna clave de API.

    El repositorio es público: una clave acá la puede usar cualquiera.
    """
    patrones = [
        (r"AIza[0-9A-Za-z_\-]{30,}", "clave de Google"),
        (r"AQ\.[0-9A-Za-z_\-]{30,}", "clave de Google AI"),
        (r"sk-[0-9A-Za-z]{30,}", "clave de OpenAI"),
        (r"gh[pous]_[0-9A-Za-z]{30,}", "token de GitHub"),
        (r"xox[baprs]-[0-9A-Za-z\-]{20,}", "token de Slack"),
    ]
    for n in PAGINAS + ["sw.js"]:
        if not os.path.exists(os.path.join(RAIZ, n)):
            continue
        txt = leer(n)
        for pat, que in patrones:
            if re.search(pat, txt):
                error("secretos", "%s parece tener una %s escrita dentro" % (n, que))


def r_ids():
    """Que no se pida un elemento que no existe en la página.

    getElementById('algo') sobre un id que no está devuelve null y la
    función se cae sin aviso.
    """
    for n in PAGINAS:
        if not os.path.exists(os.path.join(RAIZ, n)):
            continue
        txt = leer(n)
        # Un id puede estar en el HTML, dentro de una plantilla de JavaScript
        # o asignarse al vuelo con elemento.id = 'algo'. Las tres cuentan.
        presentes = set(re.findall(r'id="([^"]+)"', txt))
        presentes |= set(re.findall(r"id='([^']+)'", txt))
        presentes |= set(re.findall(r"\.id\s*=\s*['\"]([^'\"]+)['\"]", txt))
        # ids que se arman al vuelo, tipo id="fee-prod-'+r.id+'"
        dinamicos = set(re.findall(r"id=\"([a-zA-Z0-9_-]+?)-'\s*\+", txt))
        # comillas simples y dobles: las dos formas se usan en JavaScript
        usados = set(re.findall(r"getElementById\(\s*'([^']+)'\s*\)", txt))
        usados |= set(re.findall(r'getElementById\(\s*"([^"]+)"\s*\)', txt))
        usados |= set(re.findall(r"listo\('([^']+)'", txt))
        huerfanos = sorted(u for u in usados - presentes
                           if not any(u.startswith(d) for d in dinamicos))
        if huerfanos:
            error("ids", "%s llama a elementos que no existen: %s"
                  % (n, ", ".join(huerfanos)))


def r_onclick():
    """Que cada onclick llame a una función que exista.

    Un onclick roto no avisa: el botón simplemente no hace nada.
    """
    for n in PAGINAS:
        if not os.path.exists(os.path.join(RAIZ, n)):
            continue
        txt = leer(n)
        js = "\n".join(scripts_de(txt))
        definidas = set(re.findall(r"function\s+([A-Za-z_$][\w$]*)\s*\(", js))
        definidas |= set(re.findall(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*function", js))
        definidas |= set(re.findall(r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", js))
        nativas = {"alert", "confirm", "prompt", "event", "window", "document",
                   "console", "setTimeout", "parseInt", "parseFloat", "Number",
                   "String", "JSON", "Math", "Date", "location", "history", "this",
                   "encodeURIComponent", "decodeURIComponent", "isNaN", "Object",
                   "Array", "Boolean", "RegExp", "Promise", "fetch"}
        # palabras del lenguaje que van seguidas de paréntesis pero no son funciones
        palabras = {"if", "for", "while", "switch", "catch", "return", "typeof",
                    "new", "delete", "void", "in", "of", "do", "else", "function"}
        llamadas = set()
        for at in re.findall(r'on(?:click|change|input|submit)="([^"]+)"', txt):
            # solo nombres sueltos: descarta metodos (algo.metodo()) y palabras clave
            for f in re.findall(r"(?<![.\w$])([A-Za-z_$][\w$]*)\s*\(", at):
                if f not in palabras:
                    llamadas.add(f)
        faltan = sorted(f for f in llamadas - definidas - nativas)
        if faltan:
            error("onclick", "%s tiene botones que llaman a funciones inexistentes: %s"
                  % (n, ", ".join(faltan)))


def r_duplicadas():
    """Que ninguna función esté definida dos veces.

    La segunda pisa a la primera en silencio y el comportamiento cambia
    según dónde quedó cada una.
    """
    for n in PAGINAS:
        if not os.path.exists(os.path.join(RAIZ, n)):
            continue
        js = "\n".join(scripts_de(leer(n)))
        nombres = re.findall(r"^\s*function\s+([A-Za-z_$][\w$]*)\s*\(", js, re.M)
        vistos, dup = set(), set()
        for x in nombres:
            (dup if x in vistos else vistos).add(x)
        if dup:
            error("duplicadas", "%s define dos veces: %s" % (n, ", ".join(sorted(dup))))


def r_version():
    """Que la versión sea la misma en todas partes.

    Si el service worker no cambia de nombre, los teléfonos siguen
    mostrando la versión vieja aunque el archivo nuevo esté publicado.
    """
    vistas = {}
    for n in PAGINAS:
        if not os.path.exists(os.path.join(RAIZ, n)):
            continue
        m = re.search(r'name="app-version"\s+content="([^"]+)"', leer(n))
        if not m:
            error("version", "%s no declara <meta name=\"app-version\">" % n)
        else:
            vistas[n] = m.group(1)
    mf = os.path.join(RAIZ, "manifest.webmanifest")
    if os.path.exists(mf):
        try:
            vistas["manifest.webmanifest"] = json.load(open(mf, encoding="utf-8")).get("version", "")
        except Exception:
            pass
    distintas = set(v for v in vistas.values() if v)
    if len(distintas) > 1:
        error("version", "las versiones no coinciden: " +
              ", ".join("%s=%s" % (k, v) for k, v in sorted(vistas.items())))


def r_sw():
    """Que el service worker sirva los archivos que existen."""
    ruta = os.path.join(RAIZ, "sw.js")
    if not os.path.exists(ruta):
        return
    sw = leer("sw.js")
    if not re.search(r"CACHE\s*=\s*'[^']+'", sw):
        error("sw", "sw.js no define un nombre de caché")
    locales = re.findall(r"'\./([^']+)'", sw)
    for f in locales:
        if f and not os.path.exists(os.path.join(RAIZ, f)):
            error("sw", "sw.js guarda en caché un archivo que no existe: " + f)
    for p in PAGINAS:
        if "./" + p not in sw:
            aviso("sw", "%s no está en la lista del service worker" % p)


def r_enlaces():
    """Que los enlaces entre las tres páginas apunten a algo que existe."""
    for n in PAGINAS:
        if not os.path.exists(os.path.join(RAIZ, n)):
            continue
        for destino in set(re.findall(r'href="\./([a-zA-Z0-9_.-]+\.html)"', leer(n))):
            if not os.path.exists(os.path.join(RAIZ, destino)):
                error("enlaces", "%s enlaza a %s, que no existe" % (n, destino))


def r_datos():
    """Que datos.json tenga la forma que la app espera."""
    ruta = os.path.join(RAIZ, "datos.json")
    if not os.path.exists(ruta):
        return
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        return
    for clave in ("gdd", "coords", "frost", "meta"):
        if clave not in d:
            error("datos", "datos.json no trae la sección '%s'" % clave)
    gdd = d.get("gdd", {})
    if not gdd:
        error("datos", "datos.json no tiene ninguna estación con grados-día")
        return
    est = next(iter(gdd))
    fila = gdd[est][0] if gdd[est] else None
    if not fila or len(fila) < 3:
        error("datos", "las filas de grados-día no tienen fecha, base 4,5 y base 10")
    sin_coord = [e for e in gdd if e not in d.get("coords", {})]
    if sin_coord:
        aviso("datos", "%d estaciones sin coordenada (no se pueden ubicar ni sugerir por GPS): %s"
              % (len(sin_coord), ", ".join(sorted(sin_coord)[:5])))
    # las estaciones ocultas deben existir
    cfg = os.path.join(RAIZ, "config.json")
    if os.path.exists(cfg):
        try:
            off = json.load(open(cfg, encoding="utf-8")).get("off", [])
            fantasma = [e for e in off if e not in gdd]
            if fantasma:
                aviso("datos", "config.json oculta estaciones que ya no existen: " +
                      ", ".join(fantasma))
        except Exception:
            pass
    # aviso de datos viejos
    fechas = [f[0] for arr in gdd.values() if arr for f in [arr[-1]]]
    if fechas:
        import datetime
        ult = max(fechas)
        try:
            dias = (datetime.date.today() - datetime.date(*map(int, ult.split("-")))).days
            if dias > 14:
                aviso("datos", "el último dato climático es del %s, hace %d días — toca subir el Excel"
                      % (ult, dias))
        except Exception:
            pass


def r_cuarteles():
    """Que la base de productores tenga las columnas que la app usa."""
    ruta = os.path.join(RAIZ, "cuarteles.json")
    if not os.path.exists(ruta):
        return
    try:
        c = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        return
    if not isinstance(c, list) or not c:
        error("cuarteles", "cuarteles.json debería ser una lista con filas")
        return
    for col in ("R_Social", "Cuartel", "Variedad", "Zona", "Cod_Cuartel"):
        if col not in c[0]:
            error("cuarteles", "a cuarteles.json le falta la columna '%s'" % col)
    codigos = [x.get("Cod_Cuartel") for x in c]
    rep = set(x for x in codigos if codigos.count(x) > 1)
    if rep:
        aviso("cuarteles", "códigos de cuartel repetidos: " + ", ".join(sorted(map(str, rep))[:5]))


def r_fenologia():
    """Que las tres listas de estados fenológicos tengan el mismo largo.

    Si no calzan, un estado queda sin color o sin sigla y el gráfico de
    avance se descuadra.
    """
    ruta = os.path.join(RAIZ, "tecnica.html")
    if not os.path.exists(ruta):
        return
    js = "\n".join(scripts_de(leer("tecnica.html")))
    largos = {}
    for nombre in ("FENO_ESTADOS", "FENO_SIGLAS", "FENO_COLORS"):
        m = re.search(nombre + r"\s*=\s*\[(.*?)\]", js, re.S)
        if not m:
            error("fenologia", "tecnica.html no define " + nombre)
        else:
            largos[nombre] = len(re.findall(r'["\']', m.group(1))) // 2
    if len(set(largos.values())) > 1:
        error("fenologia", "las listas de estados no calzan: " +
              ", ".join("%s=%d" % (k, v) for k, v in largos.items()))


# ─────────────────────────────────────────────────────────────
REVISIONES = [
    ("archivos del sitio", r_archivos),
    ("archivos JSON", r_json),
    ("sintaxis de JavaScript", r_sintaxis),
    ("claves de API", r_secretos),
    ("elementos de la página", r_ids),
    ("botones", r_onclick),
    ("funciones duplicadas", r_duplicadas),
    ("número de versión", r_version),
    ("service worker", r_sw),
    ("enlaces entre páginas", r_enlaces),
    ("datos climáticos", r_datos),
    ("base de cuarteles", r_cuarteles),
    ("estados fenológicos", r_fenologia),
]


def main():
    print("VERIFICACIÓN · Plataforma Exportadora Los Olmos")
    print("carpeta: %s\n" % RAIZ)
    for titulo, fn in REVISIONES:
        antes = len(errores)
        try:
            fn()
        except Exception as e:
            error(titulo, "la revisión no pudo completarse: %s" % e)
        estado = "FALLA" if len(errores) > antes else "ok"
        print("  %-26s %s" % (titulo, estado))

    if avisos:
        print("\nAVISOS (no detienen la publicación):")
        for s, m in avisos:
            print("  · [%s] %s" % (s, m))

    if errores:
        print("\nERRORES (%d):" % len(errores))
        for s, m in errores:
            print("  ✗ [%s] %s" % (s, m))
        print("\nNo publiques hasta corregir esto.")
        return 1

    print("\nTodo en orden. %d revisiones sin errores." % len(REVISIONES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
