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

    # 1 · las tres páginas abren sin errores de JavaScript
    for pagina in ["index.html", "clima.html", "tecnica.html"]:
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
