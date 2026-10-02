#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PRUEBAS FUNCIONALES · Plataforma Exportadora Los Olmos
======================================================

Abre las tres páginas en un navegador de verdad y comprueba que hagan
lo que tienen que hacer. Más lento que verificar.py, pero encuentra
cosas que solo aparecen al usar la app.

    pip install playwright && playwright install chromium
    python3 pruebas/funcional.py

Devuelve 0 si todo pasa y 1 si algo falla.

Cada prueba corresponde a algo que alguna vez se rompió de verdad:
la app en blanco, el filtro que congelaba el teléfono, los grados-día
mal calculados, las fotos que llenaban la memoria.
"""

import json
import os
import subprocess
import sys
import threading
import time
import http.server
import socketserver

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PUERTO = 8899
BASE = "http://localhost:%d" % PUERTO

resultados = []


def prueba(nombre, ok, detalle=""):
    resultados.append((nombre, bool(ok), detalle))
    print("  %-46s %s%s" % (nombre, "ok" if ok else "FALLA",
                            ("  · " + detalle) if detalle else ""))


# ── servidor local ───────────────────────────────────────────
class Silencioso(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def translate_path(self, path):
        rel = path.split("?", 1)[0].lstrip("/")
        return os.path.join(RAIZ, rel)


def servir():
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("", PUERTO), Silencioso)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ── datos de prueba ──────────────────────────────────────────
def registros_de_prueba():
    """Tres registros fenológicos inventados, sin fotos."""
    return [
        {"id": 900001, "prod": "AGRICOLA ANTUMAPU LIMITADA", "ctel": "2019",
         "vari": "AREKO", "estado": "Puntas Verdes", "fecha": "2026-08-20",
         "notas": "", "gps": {"lat": -34.5157, "lng": -70.9030, "acc": 5, "sim": False},
         "ts": "2026-08-20T12:00:00.000Z"},
        {"id": 900002, "prod": "AGRICOLA ANTUMAPU LIMITADA", "ctel": "2019",
         "vari": "AREKO", "estado": "Ramillete Expuesto", "fecha": "2026-09-01",
         "notas": "", "gps": {"lat": -34.5157, "lng": -70.9030, "acc": 5, "sim": False},
         "ts": "2026-09-01T12:00:00.000Z"},
        {"id": 900003, "prod": "AGRICOLA GORA LIMITADA", "ctel": "TRANQUE",
         "vari": "LAPINS", "estado": "Yema Hinchada", "fecha": "2026-08-25",
         "notas": "", "gps": None, "ts": "2026-08-25T12:00:00.000Z"},
    ]


def gdd_esperado(est, desde, hasta, base):
    """Calcula los grados-día directamente del archivo, para comparar."""
    d = json.load(open(os.path.join(RAIZ, "datos.json"), encoding="utf-8"))
    col = 1 if base == 4.5 else 2
    suma, dias = 0.0, 0
    for fila in d["gdd"].get(est, []):
        if desde <= fila[0] <= hasta and fila[col] is not None:
            suma += fila[col]
            dias += 1
    return (round(suma, 1), dias) if dias else (None, 0)


# ── pruebas ──────────────────────────────────────────────────
def correr(pw):
    nav = pw.chromium.launch()

    # 1 · todas las páginas abren sin errores de JavaScript
    for pagina in ["index.html", "clima.html", "tecnica.html", "tecnico.html", "sag.html"]:
        ctx = nav.new_context(viewport={"width": 390, "height": 844})
        pg = ctx.new_page()
        fallas = []
        pg.on("pageerror", lambda e: fallas.append(str(e)))
        pg.goto("%s/%s" % (BASE, pagina), wait_until="domcontentloaded")
        pg.wait_for_timeout(4000)
        # los errores por librerías bloqueadas no cuentan: son de red, no del código
        reales = [f for f in fallas if "librer" not in f.lower()]
        prueba("%s abre sin errores" % pagina, not reales,
               reales[0][:60] if reales else "")
        ctx.close()

    # 2 · la portada muestra indicadores con valores
    ctx = nav.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto("%s/index.html" % BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(4500)
    kpis = pg.evaluate("""() => ['kGdd','kFrost','kFeno','kCont'].map(i => {
        const e = document.getElementById(i);
        return e ? e.textContent.trim() : '';
    })""")
    prueba("la portada calcula sus indicadores",
           all(k and k != "—" for k in kpis), " / ".join(kpis))
    ctx.close()

    # 3 · la Climática carga los datos del clima
    ctx = nav.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto("%s/clima.html" % BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)
    est = pg.evaluate("() => (typeof ESTACIONES!=='undefined') ? ESTACIONES.length : 0")
    prueba("la Climática carga datos.json", est > 0, "%d estaciones" % est)
    ctx.close()

    # 4 · la Plataforma de Campo, con registros de prueba
    ctx = nav.new_context(viewport={"width": 390, "height": 844},
                          geolocation={"latitude": -34.5157, "longitude": -70.9030},
                          permissions=["geolocation"])
    pg = ctx.new_page()
    fallas = []
    pg.on("pageerror", lambda e: fallas.append(str(e)))
    pg.on("dialog", lambda d: d.accept())
    pg.goto("%s/tecnica.html" % BASE, wait_until="domcontentloaded")
    pg.evaluate("r => localStorage.setItem('olo4_feno', JSON.stringify(r))",
                registros_de_prueba())
    pg.reload(wait_until="domcontentloaded")
    pg.wait_for_timeout(5000)

    # 4a · la base de cuarteles llega
    n = pg.evaluate("() => cuartelesDB.length")
    prueba("carga la base de cuarteles", n > 0, "%d cuarteles" % n)

    # 4b · los registros antiguos reciben su código de estado
    cod = pg.evaluate("() => fenologicos.filter(r => codDeReg(r) != null).length")
    prueba("asigna código de estado a los registros", cod == 3, "%d de 3" % cod)

    # 4c · la estación más cercana por GPS
    cerca = pg.evaluate("""async () => {
        await cargarClima();
        const c = estacionCercana(-34.5157, -70.9030);
        return c ? {est: c.est, km: c.km} : null;
    }""")
    prueba("encuentra la estación más cercana",
           cerca and cerca["km"] < 5,
           "%s a %.1f km" % (cerca["est"], cerca["km"]) if cerca else "no encontró ninguna")

    # 4d · los grados-día coinciden con el archivo
    esperado, dias_esp = gdd_esperado("Antumapu - Los Lingues", "2026-07-01", "2026-09-01", 10)
    calc = pg.evaluate("""async () => {
        await cargarClima();
        const a = gddAcum('Antumapu - Los Lingues', '2026-07-01', '2026-09-01', 10);
        return a ? {gdd: a.gdd, dias: a.dias} : null;
    }""")
    prueba("los grados-día cuadran con datos.json",
           calc and abs(calc["gdd"] - esperado) < 0.05 and calc["dias"] == dias_esp,
           "app %s · archivo %s" % (calc["gdd"] if calc else "—", esperado))

    # 4e · guardar un registro deja los grados-día pegados
    guardado = pg.evaluate("""async () => {
        await cargarClima();
        openSec('fenologia');
        llenarSelectEstaciones();
        document.getElementById('fe-prod').value = 'PRUEBA';
        document.getElementById('fe-ctel').value = 'C1';
        document.getElementById('fe-var').value = 'LAPINS';
        document.getElementById('fe-fecha').value = '2026-09-01';
        const s = document.getElementById('fe-estado');
        s.value = 'Flor Abierta';
        document.getElementById('fe-est').value = 'Antumapu - Los Lingues';
        onEstManual();
        const antes = fenologicos.length;
        saveFeno();
        const r = fenologicos[0];
        return {creado: fenologicos.length === antes + 1, est: r.est,
                gdd10: r.gdd10, cod: r.cod, sigla: r.sigla, temp: r.temp};
    }""")
    prueba("guarda un registro con estación y grados-día",
           guardado["creado"] and guardado["est"] and guardado["gdd10"] is not None
           and guardado["cod"] == 6,
           "%s · %s °D · %s" % (guardado["est"], guardado["gdd10"], guardado["sigla"]))

    # 4f · el filtro filtra de verdad y no congela
    pg.evaluate("() => abrirFenoHist()")
    pg.wait_for_timeout(2000)
    t0 = time.time()
    filtro = pg.evaluate("""() => {
        const sel = document.getElementById('feno-filter-prod');
        const todas = document.querySelectorAll('.fh-card').length;
        sel.value = 'AGRICOLA ANTUMAPU LIMITADA';
        onFenoFilterChange();
        return {todas, filtradas: document.querySelectorAll('.fh-card').length};
    }""")
    ms = (time.time() - t0) * 1000
    prueba("el filtro reduce los resultados",
           filtro["filtradas"] < filtro["todas"] and filtro["filtradas"] > 0,
           "%d → %d" % (filtro["todas"], filtro["filtradas"]))
    prueba("el filtro responde rápido", ms < 1500, "%.0f ms" % ms)

    # 4g · las fotos no se pegan como texto dentro de la página
    pg.evaluate("() => { document.getElementById('feno-filter-prod').value=''; onFenoFilterChange(); }")
    pg.wait_for_timeout(1200)
    peso = pg.evaluate("""() => {
        const im = [...document.querySelectorAll('img')].filter(i => (i.src||'').startsWith('data:'));
        return im.reduce((s, i) => s + i.src.length, 0);
    }""")
    prueba("las fotos no inflan la página", peso < 500000,
           "%.2f MB en imágenes incrustadas" % (peso / 1024 / 1024))

    reales = [f for f in fallas if "librer" not in f.lower()]
    prueba("ninguna acción provocó un error", not reales,
           reales[0][:60] if reales else "")
    ctx.close()

    # 5 · Departamento Técnico
    ctx = nav.new_context(viewport={"width": 1440, "height": 950})
    pg = ctx.new_page()
    fallas = []
    pg.on("pageerror", lambda e: fallas.append(str(e)))
    pg.goto("%s/tecnico.html" % BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(4000)

    d = pg.evaluate("""() => D ? {flujo: D.flujo.length, est: D.estimaciones.length} : null""")
    prueba("Depto. Técnico carga cosecha.json", d and d["flujo"] > 0,
           "%d filas de calendario · %d estimaciones" % (d["flujo"], d["est"]) if d else "")

    soon = pg.evaluate("() => document.querySelectorAll('.esp-c.soon').length")
    prueba("cinco especies quedan en construcción", soon == 5, "%d marcadas" % soon)

    # los kilos del calendario deben cuadrar con el archivo
    cos = json.load(open(os.path.join(RAIZ, "cosecha.json"), encoding="utf-8"))
    kg_arch = sum(sum(r["dias"].values()) for r in cos["flujo"])
    pg.evaluate("() => ir('flujo')")
    pg.wait_for_timeout(1800)
    kg_app = pg.evaluate("""() => {
        const t = document.querySelector('#t-flujo .tot td:nth-child(4)');
        return t ? Number(t.textContent.replace(/\./g,'')) : 0;
    }""")
    prueba("el calendario suma lo mismo que el archivo",
           abs(kg_app - kg_arch) < 2, "app %s · archivo %s" % (kg_app, round(kg_arch)))

    # abrir una semana muestra sus días
    abierta = pg.evaluate("""() => {
        const s = D.flujo.flatMap(r => Object.keys(r.dias));
        const sem = new Date(s[0] + 'T00:00:00');
        const antes = document.querySelectorAll('#t-flujo thead tr').length;
        const n = [...document.querySelectorAll('#t-flujo thead th.wk')][3];
        if (n) n.click();
        return {antes, despues: document.querySelectorAll('#t-flujo thead tr').length};
    }""")
    prueba("al abrir una semana aparecen sus días",
           abierta["despues"] > abierta["antes"],
           "%d → %d filas de encabezado" % (abierta["antes"], abierta["despues"]))

    # Kilos Semana tiene que cuadrar con el calendario
    pg.evaluate("() => ir('kilos')")
    pg.wait_for_timeout(1800)
    ks = pg.evaluate("""() => {
        const t = document.querySelector('#t-kilos .tot td:last-child');
        return t ? Number(t.textContent.replace(/\./g,'')) : 0;
    }""")
    prueba("Kilos Semana cuadra con el calendario",
           abs(ks - kg_arch) < 2, "%s vs %s" % (ks, round(kg_arch)))

    reales = [f for f in fallas if "librer" not in f.lower()]
    prueba("el Depto. Técnico no da errores", not reales,
           reales[0][:60] if reales else "")
    ctx.close()

    # 6 · Requisitos SAG
    ctx = nav.new_context(viewport={"width": 1440, "height": 950})
    pg = ctx.new_page()
    fallas = []
    pg.on("pageerror", lambda e: fallas.append(str(e)))
    pg.goto("%s/sag.html" % BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(4000)

    # el inventario de CSG se arma solo desde cuarteles.json y cosecha.json
    cuart = json.load(open(os.path.join(RAIZ, "cuarteles.json"), encoding="utf-8"))
    cos = json.load(open(os.path.join(RAIZ, "cosecha.json"), encoding="utf-8"))
    esperados = {str(r["CSG"]) for r in cuart if r.get("CSG")}
    esperados |= {str(r["csg"]) for r in cos["flujo"] if r.get("csg")}
    esperados |= {str(r["csg"]) for r in cos["estimaciones"] if r.get("csg")}
    n = pg.evaluate("() => CSG.length")
    prueba("reúne todos nuestros CSG", n == len(esperados),
           "%d de %d" % (n, len(esperados)))

    con_nombre = pg.evaluate("() => CSG.filter(c => c.nombre).length")
    prueba("cada CSG tiene productor", con_nombre == n,
           "%d de %d con nombre" % (con_nombre, n))

    # la agenda de pesticidas se carga por especie, no todo de una vez
    pg.evaluate("() => ir('pest')")
    pg.wait_for_timeout(3000)
    p = pg.evaluate("""() => PEST ? {
        esp: PEST_CLAVE, filas: PEST.filas.length,
        mer: PEST.mercados.length, sus: PEST.sustancias.length} : null""")
    idx = json.load(open(os.path.join(RAIZ, "pesticidas.json"), encoding="utf-8"))
    cer = [e for e in idx["especies"] if e["especie"] == "CEREZAS"]
    prueba("la agenda abre en cerezas", p and p["esp"] == "CEREZAS" and
           (not cer or p["filas"] == cer[0]["filas"]),
           "%d filas · %d mercados" % (p["filas"], p["mer"]) if p else "")

    # los LMR que el Excel había convertido en fecha llegan arreglados
    rep = pg.evaluate("""() => {
        const i = PEST.sustancias.indexOf('AZOXYSTROBIN/TEBUCONAZOLE');
        const j = PEST.mercados.indexOf('CHILE');
        const f = PEST.filas.find(x => x[1] === i && x[0] === j);
        const s = PEST.sustancias.indexOf('AZOXYSTROBIN');
        const g = PEST.filas.find(x => x[1] === s && x[0] === j);
        return {par: f ? f[3] : null, simple: g ? g[3] : null};
    }""")
    prueba("ningún LMR quedó convertido en fecha",
           rep["par"] == "2/4" and rep["simple"] == "2",
           "mezcla %s · simple %s" % (rep["par"], rep["simple"]))
    sin_fecha = pg.evaluate("""() => PEST.filas
        .filter(f => /^\d{4}-\d{2}-\d{2}$/.test(String(f[3]))).length""")
    prueba("no hay fechas en la columna de ppm", sin_fecha == 0,
           "%d filas con fecha" % sin_fecha)

    # el buscador filtra de verdad
    filtrado = pg.evaluate("""() => {
        const todo = filtrarPest().length;
        document.getElementById('p-mer').value = 'CHINA';
        const chi = filtrarPest().length;
        document.getElementById('p-sus').value = 'azoxy';
        const uno = filtrarPest().length;
        document.getElementById('p-mer').value = '';
        document.getElementById('p-sus').value = '';
        return {todo, chi, uno};
    }""")
    prueba("el buscador de LMR filtra",
           filtrado["todo"] > filtrado["chi"] > filtrado["uno"] > 0,
           "%d → %d → %d" % (filtrado["todo"], filtrado["chi"], filtrado["uno"]))

    # buscar sin tildes tiene que encontrar igual
    tildes = pg.evaluate("""() => {
        document.getElementById('p-sus').value = 'JAPON';
        const a = norm('JAPÓN') === norm('japon');
        document.getElementById('p-sus').value = '';
        return a;
    }""")
    prueba("la búsqueda ignora los acentos", tildes)

    # el cruce con el consolidado del SAG, con un archivo armado a mano
    primeros = sorted(esperados)[:3]
    cruce = pg.evaluate("""(csgs) => {
        const m = [['Consolidado de campanas'],[],
          ['CSG','Razon Social','Campana','Especie','Comuna','Estado'],
          ...csgs.map((c,i) => ['CSG '+c, 'PRUEBA '+i, 'CAMPANA SUR', 'CEREZAS',
                                 'CHIMBARONGO', 'vigente']),
          ['999999','AJENO','CAMPANA SUR','CEREZAS','OTRA','vigente']];
        procesarMatriz(m, 'prueba.csv');
        const d = document.querySelectorAll('#mosca-cruce tbody')[0];
        return {
          filas: CONS.filas.length,
          dentro: document.querySelectorAll('#mosca-cruce .rowq').length,
          cols: CONS.columnas
        };
    }""", primeros)
    prueba("el cruce encuentra los CSG que están en campaña",
           cruce["dentro"] == len(primeros),
           "%d de %d · columnas %s" % (cruce["dentro"], len(primeros),
                                       ",".join(cruce["cols"])))
    prueba("lee el CSG aunque venga escrito 'CSG 91302'",
           cruce["filas"] == len(primeros) + 1,
           "%d filas leídas" % cruce["filas"])

    # un archivo sin columna CSG no puede pasar por bueno
    malo = pg.evaluate("""() => {
        const antes = CONS ? CONS.origen : null;
        try { procesarMatriz([['hola'],['a','b'],['1','2']], 'malo.csv'); } catch(e) {}
        return (CONS ? CONS.origen : null) === antes;
    }""")
    prueba("rechaza un archivo que no es el consolidado", malo)

    # un CSG que no es un número no puede pasar por "fuera de campaña"
    pend = pg.evaluate("""() => {
        const m = CSG.filter(c => !c.valido);
        const avisa = (document.getElementById('mosca-cruce').textContent || '')
                        .includes('Sin número de CSG');
        return {n: m.length, avisa, cuales: m.map(c => c.csg)};
    }""")
    prueba("los CSG incompletos se separan de los que no están en campaña",
           pend["n"] == 0 or pend["avisa"],
           "%d sin número: %s" % (pend["n"], ", ".join(pend["cuales"])))

    # si un sitio externo no se deja incrustar, aparece la tarjeta, no un marco vacío
    tarjeta = pg.evaluate("""() => {
        ir('pais');
        extNoSeVe('ext-sag', 'sag');
        const c = document.getElementById('ext-sag');
        return {card: !!c.querySelector('.ext-off'),
                iframe: !!c.querySelector('iframe'),
                link: !!c.querySelector('a[target=_blank]')};
    }""")
    prueba("un sitio que no se deja incrustar muestra tarjeta con enlace",
           tarjeta["card"] and tarjeta["link"] and not tarjeta["iframe"],
           "tarjeta=%s enlace=%s marco=%s" % (tarjeta["card"], tarjeta["link"],
                                              tarjeta["iframe"]))
    vuelve = pg.evaluate("""() => {
        extReintentar('ext-sag', 'sag');
        return !!document.getElementById('ext-sag').querySelector('iframe');
    }""")
    prueba("se puede volver a intentar incrustarlo", vuelve)

    reales = [f for f in fallas if "librer" not in f.lower()]
    prueba("Requisitos SAG no da errores", not reales,
           reales[0][:60] if reales else "")
    ctx.close()

    # 7 · Plataforma de Campo: el formato de escritorio
    ctx = nav.new_context(viewport={"width": 1440, "height": 950})
    pg = ctx.new_page()
    fallas = []
    pg.on("pageerror", lambda e: fallas.append(str(e)))
    pg.goto("%s/tecnica.html" % BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(4500)

    pc = pg.evaluate("""() => ({
        anchoDoc: document.documentElement.scrollWidth,
        anchoVent: window.innerWidth,
        barraArriba: getComputedStyle(document.querySelector('.app-header')).display,
        navAbajo: getComputedStyle(document.getElementById('bnav')).display,
        scrollInterno: getComputedStyle(document.querySelector('.app-content')).overflowY,
        rejilla: getComputedStyle(document.getElementById('view-hub')).display
    })""")
    prueba("en el monitor no sobra ancho", pc["anchoDoc"] <= pc["anchoVent"],
           "%d de %d px" % (pc["anchoDoc"], pc["anchoVent"]))
    prueba("una sola barra de desplazamiento", pc["scrollInterno"] == "visible",
           "el contenido ya no tiene la suya")
    prueba("sin barra superior ni menú inferior duplicados",
           pc["barraArriba"] == "none" and pc["navAbajo"] == "none")
    prueba("las secciones usan la rejilla de escritorio", pc["rejilla"] == "grid")

    # las fichas y los campos dejan de ser barras de lado a lado
    anchos = pg.evaluate("""() => {
        openSec('feno');
        const o = [...document.querySelectorAll('#view-feno-hub > .fh-opt')];
        const cont = document.querySelector('.app-content').clientWidth;
        return {n: o.length, max: Math.max(...o.map(e => e.offsetWidth)), cont};
    }""")
    prueba("las filas de menú se ponen de a tres",
           anchos["n"] > 0 and anchos["max"] < anchos["cont"] * .4,
           "%d fichas de %d px en %d" % (anchos["n"], anchos["max"], anchos["cont"]))

    campos = pg.evaluate("""() => {
        openSec('fenologia');
        const c = [...document.querySelectorAll('#view-fenologia > .sel-card')];
        const cont = document.querySelector('.app-content').clientWidth;
        return {n: c.length, max: Math.max(...c.map(e => e.offsetWidth)), cont};
    }""")
    prueba("los campos del formulario se ponen de a tres",
           campos["n"] > 0 and campos["max"] < campos["cont"] * .4,
           "%d campos de %d px en %d" % (campos["n"], campos["max"], campos["cont"]))

    # el título ya no dice que esto es el Departamento Técnico
    titulos = pg.evaluate("""() => {
        goHub();            // la barra muestra el título de la vista abierta
        return {
        hub: document.querySelector('.hub-g-title').textContent.trim(),
        barra: document.getElementById('h-title').textContent.trim(),
        mayus: [...document.querySelectorAll('.sec-hdr-sub')]
                 .map(e => e.textContent.trim())
                 .filter(t => t && t === t.toUpperCase() && /[A-ZÁÉÍÓÚÑ]{4}/.test(t))
        };
    }""")
    prueba("el módulo se llama Plataforma de Campo",
           titulos["hub"] == "Plataforma de Campo" and titulos["barra"] == "Plataforma de Campo",
           "%s · %s" % (titulos["hub"], titulos["barra"]))
    prueba("ningún subtítulo quedó en mayúsculas", not titulos["mayus"],
           ", ".join(titulos["mayus"][:3]))

    reales = [f for f in fallas if "librer" not in f.lower()]
    prueba("la Plataforma de Campo no da errores en el monitor", not reales,
           reales[0][:60] if reales else "")
    ctx.close()

    # 8 · ...y en el teléfono sigue tal cual estaba
    ctx = nav.new_context(viewport={"width": 390, "height": 844})
    pg = ctx.new_page()
    fallas = []
    pg.on("pageerror", lambda e: fallas.append(str(e)))
    pg.goto("%s/tecnica.html" % BASE, wait_until="domcontentloaded")
    pg.wait_for_timeout(4500)
    cel = pg.evaluate("""() => ({
        anchoDoc: document.documentElement.scrollWidth,
        anchoVent: window.innerWidth,
        anchoCuerpo: getComputedStyle(document.body).maxWidth,
        barraArriba: getComputedStyle(document.querySelector('.app-header')).display,
        vista: getComputedStyle(document.getElementById('view-hub')).display,
        portada: getComputedStyle(document.querySelector('.hub-greet')).backgroundColor,
        iconoKpi: getComputedStyle(document.querySelector('.hub-kpi-ic')).display
    })""")
    prueba("en el teléfono no aparece barra lateral de lado",
           cel["anchoDoc"] <= cel["anchoVent"],
           "%d de %d px" % (cel["anchoDoc"], cel["anchoVent"]))
    prueba("el teléfono conserva su formato de 480 px",
           cel["anchoCuerpo"] == "480px" and cel["vista"] == "block",
           "%s · %s" % (cel["anchoCuerpo"], cel["vista"]))
    prueba("el teléfono conserva su barra y su portada verde",
           cel["barraArriba"] == "flex" and cel["portada"] == "rgb(30, 91, 51)"
           and cel["iconoKpi"] != "none")
    reales = [f for f in fallas if "librer" not in f.lower()]
    prueba("la Plataforma de Campo no da errores en el teléfono", not reales,
           reales[0][:60] if reales else "")
    ctx.close()
    nav.close()


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Falta Playwright. Instálalo con:")
        print("    pip install playwright && playwright install chromium")
        return 2

    print("PRUEBAS FUNCIONALES · Plataforma Exportadora Los Olmos")
    print("carpeta: %s\n" % RAIZ)
    srv = servir()
    time.sleep(1)
    try:
        with sync_playwright() as pw:
            correr(pw)
    finally:
        srv.shutdown()

    fallaron = [r for r in resultados if not r[1]]
    print("")
    if fallaron:
        print("FALLARON %d de %d pruebas:" % (len(fallaron), len(resultados)))
        for n, _, d in fallaron:
            print("  ✗ %s%s" % (n, ("  · " + d) if d else ""))
        return 1
    print("Las %d pruebas pasaron." % len(resultados))
    return 0


if __name__ == "__main__":
    sys.exit(main())
