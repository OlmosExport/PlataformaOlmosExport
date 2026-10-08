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
PAGINAS = ["index.html", "clima.html", "tecnica.html", "tecnico.html", "sag.html"]
JSONS = ["datos.json", "config.json", "cuarteles.json", "cosecha.json",
         "pesticidas.json", "fertilizacion.json", "precios.json",
         "heladas_comunas.json",
         "manifest.webmanifest"]
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
        # flecha de un solo argumento sin paréntesis:  const esc=s=>...
        definidas |= set(re.findall(
            r"(?:var|let|const)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s+)?[A-Za-z_$][\w$]*\s*=>", js))
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


def r_cosecha():
    """Que cosecha.json traiga lo que la página de Depto. Técnico espera."""
    ruta = os.path.join(RAIZ, "cosecha.json")
    if not os.path.exists(ruta):
        return
    try:
        c = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        return
    for k in ("meta", "flujo", "estimaciones", "kilosSemana"):
        if k not in c:
            error("cosecha", "cosecha.json no trae la sección '%s'" % k)
    if not c.get("flujo"):
        error("cosecha", "cosecha.json no tiene filas de calendario")
        return
    f0 = c["flujo"][0]
    for campo in ("prod", "vari", "kg", "dias"):
        if campo not in f0:
            error("cosecha", "a las filas del calendario les falta '%s'" % campo)
    # el recálculo de kilos semana tiene que cuadrar con el calendario
    kg_cal = sum(sum(r.get("dias", {}).values()) for r in c["flujo"])
    kg_sem = sum(sum(r.get("kg", {}).values()) for r in c.get("kilosSemana", {}).get("filas", []))
    if kg_cal and abs(kg_cal - kg_sem) > 1:
        error("cosecha", "Kilos Semana (%s) no cuadra con el calendario (%s)"
              % (round(kg_sem), round(kg_cal)))
    xls = c.get("kilosSemanaExcel", {}).get("filas", [])
    if xls:
        kx = sum(sum(r.get("kg", {}).values()) for r in xls)
        if abs(kg_cal - kx) > 1:
            aviso("cosecha", "la tabla dinámica del Excel está %s kg atrás del calendario"
                  % f"{abs(kg_cal-kx):,.0f}".replace(",", "."))


def r_pesticidas():
    """Que la agenda de pesticidas esté completa y avisar si está vieja.

    El índice nombra un archivo por especie. Si falta uno, la búsqueda
    de LMR queda en blanco justo cuando se necesita.
    """
    ruta = os.path.join(RAIZ, "pesticidas.json")
    if not os.path.exists(ruta):
        return
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        return
    esp = d.get("especies") or []
    if not esp:
        error("pesticidas", "pesticidas.json no lista ninguna especie")
        return
    import datetime
    hoy = datetime.date.today()
    for e in esp:
        arch = e.get("archivo", "")
        p = os.path.join(RAIZ, arch)
        if not arch or not os.path.exists(p):
            error("pesticidas", "falta el archivo de %s: %s" % (e.get("especie"), arch))
            continue
        try:
            h = json.load(open(p, encoding="utf-8"))
        except Exception:
            error("pesticidas", "%s no es un JSON válido" % arch)
            continue
        if len(h.get("filas") or []) != e.get("filas"):
            error("pesticidas", "%s dice %s filas y el índice dice %s"
                  % (arch, len(h.get("filas") or []), e.get("filas")))
        for clave in ("mercados", "sustancias", "tipos", "campos"):
            if not h.get(clave):
                error("pesticidas", "%s no trae la sección '%s'" % (arch, clave))
        # ningún índice de la fila puede apuntar fuera del diccionario
        nm, ns, nt = len(h.get("mercados", [])), len(h.get("sustancias", [])), len(h.get("tipos", []))
        for f in (h.get("filas") or [])[:5000]:
            if not (0 <= f[0] < nm and 0 <= f[1] < ns and 0 <= f[2] < nt):
                error("pesticidas", "%s tiene una fila que apunta a un mercado o "
                                    "sustancia que no existe" % arch)
                break
        f = e.get("fecha")
        if f:
            try:
                dias = (hoy - datetime.date.fromisoformat(f)).days
                if dias > 180:
                    aviso("pesticidas", "%s se descargó hace %d días (%s)"
                          % (e.get("especie"), dias, f))
            except ValueError:
                aviso("pesticidas", "%s tiene una fecha rara: %s" % (e.get("especie"), f))
        else:
            aviso("pesticidas", "%s no trae fecha de descarga" % e.get("especie"))


def r_fertilizacion():
    """Que los cuatro programas estén completos y sigan siendo distintos.

    Si dos programas quedan iguales, alguien pisó una receta: el de vigor
    bajo y el vigoroso NO pueden repartir el nitrógeno de la misma forma.
    """
    ruta = os.path.join(RAIZ, "fertilizacion.json")
    if not os.path.exists(ruta):
        return
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        return
    progs = d.get("programas") or {}
    if len(progs) < 4:
        error("fertilizacion", "se esperaban 4 programas tipo y hay %d" % len(progs))
    for clave in ("portainjertos", "matrizN", "fuentes", "comentarios"):
        if not d.get(clave):
            error("fertilizacion", "fertilizacion.json no trae '%s'" % clave)

    firmas = {}
    for k, p in progs.items():
        for campo in ("parcializacion", "receta", "distribucion", "defecto"):
            if not p.get(campo):
                error("fertilizacion", "%s no trae '%s'" % (k, campo))
                break
        else:
            for n, v in p["parcializacion"].items():
                if abs(sum(v) - 1) > 0.001:
                    error("fertilizacion", "en %s el reparto de %s suma %.0f%%, no 100%%"
                          % (k, n, sum(v) * 100))
            # cada producto de la receta tiene que existir en la lista de fuentes
            for i, et in enumerate(p["receta"], 1):
                for pr in et["productos"]:
                    if pr["prod"] not in d["fuentes"]:
                        error("fertilizacion", "%s etapa %d usa '%s', que no está "
                              "en la lista de productos" % (k, i, pr["prod"]))
            kf = [x["prod"] for x in p["receta"][3]["productos"] if x["nut"] == "K"]
            firmas[k] = (tuple(p["parcializacion"]["N"]), tuple(sorted(kf)))

    vig = [k for k in firmas if "vigorosa" in k]
    baj = [k for k in firmas if "bajo" in k]
    if vig and baj and firmas[vig[0]] == firmas[baj[0]]:
        error("fertilizacion", "el programa vigoroso y el de vigor bajo quedaron "
                               "con la misma receta")
    esp = os.path.join(RAIZ, "pruebas", "esperado_fertilizacion.json")
    if not os.path.exists(esp):
        aviso("fertilizacion", "falta pruebas/esperado_fertilizacion.json, "
                               "sin eso no se puede comparar contra las planillas")


def r_precios():
    """Que el mejor precio sea de verdad el menor de la fila.

    La planilla de origen tenía esa columna mal en 74 filas; si el
    generador se rompe, acá se nota antes de publicar.
    """
    ruta = os.path.join(RAIZ, "precios.json")
    if not os.path.exists(ruta):
        return
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except Exception:
        return
    prods = d.get("productos") or []
    if not prods:
        error("precios", "precios.json no trae ningún producto")
        return
    if not d.get("proveedores"):
        error("precios", "precios.json no trae la lista de proveedores")

    malos, ceros, sin = 0, 0, 0
    for p in prods:
        v = list((p.get("precios") or {}).values())
        if any(x <= 0 for x in v):
            ceros += 1
        if not v:
            sin += 1
            if p.get("mejor") is not None:
                error("precios", "%s no tiene precios pero trae un mejor precio"
                      % p.get("nombre"))
            continue
        if p.get("mejor") is None or abs(p["mejor"] - min(v)) > 0.001:
            malos += 1
        elif p["precios"].get(p.get("prov")) != p["mejor"]:
            malos += 1
    if malos:
        error("precios", "en %d productos el mejor precio no es el menor de la fila" % malos)
    if ceros:
        error("precios", "%d productos traen un precio en cero o negativo" % ceros)
    if sin:
        aviso("precios", "%d productos no tienen precio en ningún proveedor" % sin)
    if d["meta"].get("sospechosos"):
        aviso("precios", "%d productos tienen un proveedor 20 veces más caro que el "
              "más barato: revisar la unidad en la planilla" % d["meta"]["sospechosos"])


def r_fertbeta():
    """El libro del formato unificado, convertido en fertbeta.json.

    Revisa que estén las seis piezas que la página necesita y que no se
    contradigan entre sí: cada combinación de especie + grupo variedad
    que ofrecen las listas tiene que tener fenología y fecha de inicio,
    y cada producto de las listas tiene que estar en el catálogo (o
    quedar anotado como aviso, que es lo que pasa con «Humus casa»).
    """
    ruta = os.path.join(RAIZ, "fertbeta.json")
    if not os.path.exists(ruta):
        error("fertbeta", "falta fertbeta.json")
        return
    try:
        d = json.load(open(ruta, encoding="utf-8"))
    except Exception as e:
        error("fertbeta", "fertbeta.json no se puede leer: %s" % e)
        return

    for k in ("catalogo", "listas", "fenologia", "inicios", "requerimientos",
              "ejemplos", "leeme"):
        if not d.get(k):
            error("fertbeta", "fertbeta.json no trae «%s»" % k)
    if not d.get("anoTemporada"):
        error("fertbeta", "fertbeta.json no trae el año de temporada")

    cat = d.get("catalogo") or []
    nombres = {p["nombre"] for p in cat}
    if len(nombres) != len(cat):
        error("fertbeta", "hay productos repetidos en el catálogo")
    for p in cat:
        if p.get("tipo") not in ("Base", "Complementario"):
            error("fertbeta", "«%s» no es ni base ni complementario" % p.get("nombre"))
        for n in ("N", "P2O5", "K2O", "CaO", "MgO", "S"):
            v = p.get(n)
            if not isinstance(v, (int, float)) or v < 0 or v > 100:
                error("fertbeta", "la ley %s de «%s» no es un porcentaje válido: %r"
                      % (n, p.get("nombre"), v))
        if p.get("unidad") not in ("kg", "L"):
            error("fertbeta", "«%s» tiene una unidad rara: %r"
                  % (p.get("nombre"), p.get("unidad")))

    L = d.get("listas") or {}
    fen = d.get("fenologia") or {}
    ini = d.get("inicios") or {}
    for esp in L.get("especies", []):
        grupos = (L.get("grupos") or {}).get(esp) or []
        if not grupos:
            error("fertbeta", "%s no tiene grupos variedad" % esp)
        if not (L.get("portainjertos") or {}).get(esp):
            error("fertbeta", "%s no tiene portainjertos" % esp)
        for g in grupos:
            k = esp + "|" + g
            if k not in fen:
                error("fertbeta", "%s no tiene estados fenológicos" % k)
            if k not in ini:
                error("fertbeta", "%s no tiene fecha de inicio" % k)

    for k, estados in fen.items():
        ordenes = [e["orden"] for e in estados]
        if ordenes != sorted(ordenes) or len(set(ordenes)) != len(ordenes):
            error("fertbeta", "%s tiene los estados desordenados o repetidos" % k)
        dias = [e["dias"] for e in estados]
        if dias != sorted(dias):
            error("fertbeta", "%s tiene los días fuera de orden: %s" % (k, dias))
        if dias and dias[0] != 0:
            error("fertbeta", "%s no arranca en el día 0" % k)

    for k, v in ini.items():
        if not (1 <= v.get("mes", 0) <= 12) or not (1 <= v.get("dia", 0) <= 31):
            error("fertbeta", "la fecha de inicio de %s no es válida: %r" % (k, v))

    req = d.get("requerimientos") or {}
    for e in ("N", "P", "K", "Ca", "Mg"):
        if e not in (req.get("oxido") or {}):
            error("fertbeta", "falta el factor a óxido de %s" % e)
        for c in ("Cerezo", "Kiwi", "Otras"):
            if (req.get("absorcion") or {}).get(e, {}).get(c) is None:
                error("fertbeta", "falta el factor de absorción de %s en %s" % (e, c))

    # Los productos de las listas que no están en el catálogo entran con
    # ley cero; el extractor lo anota, así que tiene que estar avisado.
    sueltos = [n for n in (L.get("base", []) + L.get("complementarios", []))
               if n not in nombres]
    if sueltos and not d.get("avisos"):
        error("fertbeta", "hay productos fuera del catálogo (%s) sin aviso"
              % ", ".join(sueltos))
    elif sueltos:
        aviso("fertbeta", "%d producto(s) de las listas no están en el catálogo "
              "y entran con ley cero: %s" % (len(sueltos), ", ".join(sueltos)))

    for p in d.get("ejemplos") or []:
        if len(p.get("base") or []) > 7:
            error("fertbeta", "«%s» trae más de 7 fertilizantes base" % p.get("nombre"))
        if len(p.get("comp") or []) > 3:
            error("fertbeta", "«%s» trae más de 3 complementarios" % p.get("nombre"))
        for clave in list(p.get("dosis") or {}) + list(p.get("dosisComp") or {}):
            i, j = (int(x) for x in clave.split(","))
            if not (0 <= i < 41):
                error("fertbeta", "«%s» tiene una dosis en la semana %d" % (p.get("nombre"), i))


def r_clases_informe():
    """Que los informes impresos no usen clases que ya existen en la página.

    Pasó una vez: el informe del programa beta llamaba «bc» a la columna
    de complementarios, y «bc» ya era la perilla del encabezado del
    programa estándar, con display:flex. Las tres columnas se apilaban
    una sobre otra y el encabezado quedaba corrido respecto del cuerpo.

    La revisión saca del CSS los dos bloques propios de los informes y
    busca las clases del informe en lo que queda. Si aparece alguna, es
    que una regla de la página la va a pisar al imprimir.
    """
    ruta = os.path.join(RAIZ, "tecnico.html")
    if not os.path.exists(ruta):
        return
    t = open(ruta, encoding="utf-8").read()
    try:
        estilo = t[t.index("<style>"):t.index("</style>")]
    except ValueError:
        return

    # Los dos bloques de impresión, que son los dueños de esas clases.
    propios = [("/* ══ HOJA DEL INFORME ══", "\n/* aviso corto al aplicar o descargar */"),
               ("/* ══ HOJA DEL INFORME DEL PROGRAMA BETA ══",
                "\n@media (prefers-reduced-motion:reduce)")]
    resto = estilo
    quitados = 0
    for ini, fin in propios:
        if ini in resto:
            i = resto.index(ini)
            j = resto.index(fin, i) if fin in resto[i:] else len(resto)
            resto = resto[:i] + resto[j:]
            quitados += 1
    if quitados < 2:
        aviso("informes", "no encontré los dos bloques de CSS de impresión; "
              "la revisión de clases quedó incompleta")

    for abre, cierra, etiqueta in (
            ("function fbHojaInforme()", "\nfunction fbImprimir()", "informe beta"),
            ("function fertHojaInforme()", "\nfunction fertImprimir()", "informe estándar")):
        if abre not in t or cierra not in t:
            continue
        i = t.index(abre)
        bloque = t[i:t.index(cierra, i)]
        clases = set()
        for m in re.finditer(r'class="([^"${}]+)"', bloque):
            clases.update(m.group(1).split())
        for c in sorted(clases):
            for sel in _selectores_sueltos(resto, c):
                error("informes", "el %s usa la clase «%s», y la página ya la define "
                      "sin acotar (%s). Cambiale el nombre."
                      % (etiqueta, c, sel[:70]))


def _selectores_sueltos(css, clase):
    """Reglas de `css` que alcanzan a `.clase` desde cualquier parte.

    Una regla como `.cmp .vacio{…}` solo pinta dentro de `.cmp`, así que
    nunca va a tocar la hoja del informe. La que preocupa es la suelta,
    tipo `.bc{…}`, que alcanza a cualquier elemento con esa clase.
    """
    fuera = []
    for regla in re.finditer(r"([^{}]+)\{", css):
        for sel in regla.group(1).split(","):
            sel = sel.strip()
            if not sel or sel.startswith("@"):
                continue
            # El último combinador: lo que confina la regla es lo que viene antes.
            partes = re.split(r"[\s>+~]+", sel)
            ult = partes[-1]
            if not re.search(r"\.%s(?![\w-])" % re.escape(clase), ult):
                continue
            ancestros = " ".join(partes[:-1])
            if "#" in ancestros or "." in ancestros:
                continue          # está acotada a otra parte de la página
            fuera.append(sel)
    return fuera



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
    ("datos de cosecha", r_cosecha),
    ("agenda de pesticidas", r_pesticidas),
    ("programas de fertilización", r_fertilizacion),
    ("precios de agroquímicos", r_precios),
    ("libro de fertilización beta", r_fertbeta),
    ("clases de los informes", r_clases_informe),
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
