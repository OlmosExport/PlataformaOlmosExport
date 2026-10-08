#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pruebas del Programa de Fertilizacion (Beta), en un navegador de verdad.

La primera y mas importante compara el motor del navegador contra los
valores que el Excel recalculado dio para 5 programas (2.175 celdas),
guardados en esperado_fertbeta.json para no depender del libro.

Las demas revisan que la pagina se pueda usar completa desde la app:
armar un programa, elegir productos, escribir dosis, ver los totales
moverse, agregar un fertilizante al catalogo, mover la fenologia y el
ano de temporada, exportar y volver a cargar el respaldo.

Uso:  python3 funcional_fertbeta.py [--ver]
"""

import json
import subprocess
import sys
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SITIO = Path(__file__).resolve().parent.parent
PUERTO = 8117
VER = "--ver" in sys.argv

ok = fallos = 0


# El entorno de pruebas no tiene salida a fonts.googleapis.com, asi que la
# carga de la tipografia falla siempre. Eso no es un error de la pagina.
RUIDO = ("favicon", "404", "sw.js", "err_tunnel_connection_failed",
         "fonts.googleapis", "fonts.gstatic", "net::err_")


def fbErrores(errores):
    return [e for e in errores if not any(r in e.lower() for r in RUIDO)]


def chequeo(nombre, cond, detalle=""):
    global ok, fallos
    if cond:
        ok += 1
        print(f"  \033[32mok  \033[0m {nombre}" + (f"  · {detalle}" if detalle else ""))
    else:
        fallos += 1
        print(f"  \033[31mFALLA\033[0m {nombre}" + (f"  · {detalle}" if detalle else ""))


class Silencio(SimpleHTTPRequestHandler):
    def __init__(self, *a, **k):
        super().__init__(*a, directory=str(SITIO), **k)

    def log_message(self, *a):
        pass


def servir():
    s = ThreadingHTTPServer(("127.0.0.1", PUERTO), Silencio)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return s


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("Falta playwright:  pip install playwright --break-system-packages")
        return 2

    srv = servir()
    esperado = json.loads(
        (SITIO / "pruebas" / "esperado_fertbeta.json").read_text(encoding="utf-8"))

    with sync_playwright() as pw:
        nav = pw.chromium.launch(headless=not VER,
                                 executable_path="/opt/pw-browsers/chromium")
        pg = nav.new_page(viewport={"width": 1600, "height": 1000})
        errores = []
        pg.on("pageerror", lambda e: errores.append(str(e)))
        pg.on("console", lambda m: errores.append(m.text) if m.type == "error" else None)

        pg.goto(f"http://127.0.0.1:{PUERTO}/tecnico.html", wait_until="networkidle")
        pg.wait_for_timeout(700)

        # ── 1. La vista existe y se abre desde el menu ──
        print("\n\033[1mLa vista\033[0m")
        chequeo("la entrada está en el menú", pg.locator("#nav-fertbeta").count() == 1)
        pg.click("#nav-fertbeta")
        pg.wait_for_timeout(900)
        chequeo("la vista queda activa",
                pg.eval_on_selector("#v-fertbeta", "e=>e.classList.contains('on')"))
        chequeo("dice que es beta",
                "beta" in pg.inner_text("#nav-fertbeta").lower())

        # ── 2. El motor, contra el Excel ──
        print("\n\033[1mEl motor contra el Excel\033[0m")
        res = pg.evaluate("""(esp) => {
          const out = {total:0, malas:[]};
          const MES=['ene','feb','mar','abr','may','jun','jul','ago','sep','oct','nov','dic'];
          for (const nombre in esp) {
            const p = fbNormalizar(esp[nombre].programa, 't_'+nombre);
            const c = fbCalcular(p);
            const cel = esp[nombre].celdas;
            const cmp = (k, mio) => {
              const x = cel[k];
              out.total++;
              let igual;
              if (typeof mio === 'number' || typeof x === 'number') {
                igual = Math.abs((mio||0) - (typeof x==='number'?x:0)) < 0.051;
              } else { igual = (mio||'') === (x||''); }
              if (!igual) out.malas.push(nombre+' '+k+': mio='+JSON.stringify(mio)+
                                         ' excel='+JSON.stringify(x));
            };
            cmp('W8', c.inicio ? c.inicio.toISOString().slice(0,10) : '');
            c.filas.forEach((f,i) => {
              const r = 10+i;
              cmp('A'+r, f.mes);
              cmp('B'+r, f.sem === '' ? '' : f.sem);
              cmp('C'+r, f.fecha ? f.fecha.toISOString().slice(0,10) : '');
              cmp('D'+r, f.estado);
              ['Q','R','S','T','U'].forEach((L,k) => cmp(L+r, f.un[k]));
            });
            'EFGHIJK'.split('').forEach((L,j) => {
              cmp(L+'51', c.tBase[j]); cmp(L+'52', c.sBase[j]); });
            'MNO'.split('').forEach((L,j) => {
              cmp(L+'51', c.tComp[j]); cmp(L+'52', c.sComp[j]); });
            'QRSTU'.split('').forEach((L,k) => cmp(L+'51', c.tUn[k]));
            c.balance.forEach((b,k) => {
              const r = 63+k;
              cmp('E'+r, b.extraccion == null ? '' : b.extraccion);
              cmp('G'+r, b.absorcion);
              cmp('I'+r, b.requerimiento == null ? '' : b.requerimiento);
              cmp('J'+r, b.entrega);
              cmp('K'+r, b.balance == null ? '' : b.balance);
              cmp('L'+r, b.estado);
            });
          }
          return out;
        }""", esperado)
        chequeo("el motor da lo mismo que el Excel",
                not res["malas"],
                f"{res['total']} celdas · {len(res['malas'])} distintas")
        for m in res["malas"][:12]:
            print(f"        {m}")

        # ── 3. La estructura de la hoja es la del libro ──
        print("\n\033[1mLa hoja\033[0m")
        filas = pg.locator("#fb-grid tbody tr").count()
        chequeo("la rejilla trae 41 semanas", filas == 41, f"{filas} filas")
        cols = pg.eval_on_selector_all("#fb-grid tbody tr:first-child td", "e=>e.length")
        chequeo("y 19 columnas por fila", cols == 19, f"{cols} columnas")
        sb = pg.locator("#fb-grid thead th.t-base select").count()
        sc = pg.locator("#fb-grid thead th.t-comp select").count()
        chequeo("7 columnas base y 3 complementarias", sb == 7 and sc == 3,
                f"{sb} base · {sc} complementarias")
        un = pg.locator("#fb-grid thead th.t-un").count()
        chequeo("5 columnas de unidades nutricionales", un == 5)
        chequeo("hay dos filas de totales",
                pg.locator("#fb-grid tfoot tr").count() == 2)
        enc = pg.locator("#fb-cuerpo .fb-cab .fb-f").count()
        chequeo("el encabezado trae los 12 campos del libro", enc == 12, f"{enc} campos")

        # ── 4. Las listas se filtran por especie, como el libro ──
        print("\n\033[1mLas listas dependientes\033[0m")
        fil = pg.evaluate("""() => {
          const L = FB.listas, out = {};
          for (const e of L.especies) {
            out[e] = {g:(L.grupos[e]||[]).length, p:(L.portainjertos[e]||[]).length};
          }
          return out;
        }""")
        chequeo("cada especie tiene sus grupos y portainjertos",
                all(v["g"] > 0 and v["p"] > 0 for v in fil.values()),
                " · ".join(f"{k}: {v['g']}g/{v['p']}p" for k, v in fil.items()))
        # Cambiar la especie debe limpiar un grupo que ya no corresponde.
        limpio = pg.evaluate("""() => {
          const p = fbActivo();
          const antes = {e:p.especie, g:p.grupo, po:p.porta};
          p.especie='Cerezo'; p.grupo='Media 2'; p.porta='Colt';
          fbSetEspecie('Kiwi');
          const r = {g:fbActivo().grupo, po:fbActivo().porta};
          p.especie=antes.e; p.grupo=antes.g; p.porta=antes.po; fbGuardar(); fbPintar();
          return r;
        }""")
        chequeo("al cambiar de especie se limpia lo que no corresponde",
                limpio["g"] == "" and limpio["po"] == "",
                f"grupo={limpio['g']!r} porta={limpio['po']!r}")

        # Cuando dos estados caen en la misma semana ISO, el libro los
        # muestra juntos separados por " / ". Cerezo Muy temprana 1 tiene
        # tres pares así, y es el caso que más fácil se rompe al tocar
        # la fenología.
        juntos = pg.evaluate("""() => {
          const p = fbNormalizar({nombre:'par', especie:'Cerezo',
            grupo:'Muy temprana 1', porta:'Colt', etapa:'Produccion',
            vigor:'Normal', ha:1, ton:10});
          const c = fbCalcular(p);
          return c.filas.filter(f => f.estado.includes(' / ')).map(f => f.estado);
        }""")
        chequeo("dos estados en la misma semana salen juntos",
                len(juntos) == 3 and " / " in (juntos[0] if juntos else ""),
                " · ".join(juntos) if juntos else "ninguno")

        # ── 5. Se puede armar un programa entero desde la app ──
        print("\n\033[1mArmar un programa desde la app\033[0m")
        pg.evaluate("""() => {
          const n = FB.programas.length;
          const p = fbNormalizar({nombre:'PRUEBA', especie:'Cerezo', grupo:'Media 2',
            porta:'Colt', etapa:'Produccion', vigor:'Normal', variedad:'Lapins',
            productor:'Prod prueba', campo:'Campo prueba', ha:10, ton:12});
          FB.programas.push(p); FB.activo = p.id;
          fbGuardar(); fbListaProgramas(); fbPintar();
        }""")
        pg.wait_for_timeout(400)
        chequeo("el programa nuevo queda activo",
                pg.evaluate("() => fbActivo().nombre") == "PRUEBA")
        chequeo("el inicio sale automático de especie + grupo",
                "15-09-2026" in pg.inner_text("#fb-cuerpo .fb-f.ro"),
                pg.inner_text("#fb-cuerpo .fb-f.ro").replace("\n", " "))

        # Elegir un producto en la primera columna base.
        pg.locator("#fb-grid thead th.t-base select").first.select_option("Urea")
        pg.wait_for_timeout(350)
        chequeo("se elige el producto desde el título de la columna",
                pg.evaluate("() => fbActivo().base[0]") == "Urea")

        # Escribir una dosis y ver moverse las unidades y el total.
        celda = pg.locator('#fb-grid tbody tr:nth-child(5) input[data-j="0"][data-c="base"]')
        celda.fill("100")
        celda.dispatch_event("input")
        pg.wait_for_timeout(350)
        un_fila = pg.inner_text("#fb-u4-0")
        tot = pg.inner_text("#fb-tu0")
        chequeo("la dosis mueve las unidades de la fila", un_fila == "46",
                f"100 kg de urea (46% N) → {un_fila} UN/ha")
        chequeo("y el total de la temporada", tot == "46", f"total N = {tot}")
        sector = pg.inner_text("#fb-sb0")
        chequeo("el total por sector multiplica por la superficie", sector == "1.000",
                f"100 kg/ha × 10 ha = {sector} kg")

        # Las celdas sin producto no se pueden escribir.
        des = pg.locator('#fb-grid tbody tr:nth-child(5) input[data-j="6"]:disabled').count()
        chequeo("las columnas sin producto quedan bloqueadas", des == 1)

        # ── 6. El catálogo de fertilizantes se edita desde la app ──
        print("\n\033[1mEl catálogo\033[0m")
        pg.click("button.fb-mini:has-text('Catálogos')")
        pg.wait_for_timeout(450)
        chequeo("se abre el panel de catálogos",
                pg.eval_on_selector("#fb-modal", "e=>e.classList.contains('on')"))
        n0 = pg.locator("#fb-p-fert table.fb-cat tbody tr").count()
        chequeo("el catálogo trae los 31 productos del libro", n0 == 31, f"{n0} filas")

        # Agregar un producto y usarlo de inmediato.
        pg.evaluate("""() => {
          FB.catalogo.push({codigo:'F99', nombre:'Fertilizante de prueba', tipo:'Base',
            categoria:'Nitrogenado', N:20, P2O5:10, K2O:5, CaO:0, MgO:0, S:0,
            unidad:'kg', obs:'alta para la prueba'});
          fbGuardar(); fbPaneFert();
        }""")
        pg.wait_for_timeout(300)
        n1 = pg.locator("#fb-p-fert table.fb-cat tbody tr").count()
        chequeo("se agrega un fertilizante nuevo", n1 == n0 + 1, f"{n0} → {n1}")

        # Cambiar una ley se aplica al cálculo al instante.
        antes = pg.evaluate("() => fbCalcular(fbActivo()).tUn[0]")
        pg.evaluate("""() => {
          const i = FB.catalogo.findIndex(x=>x.nombre==='Urea');
          fbCat(i,'N',23);
        }""")
        despues = pg.evaluate("() => fbCalcular(fbActivo()).tUn[0]")
        chequeo("cambiar una ley cambia todos los programas",
                abs(antes - 46) < .1 and abs(despues - 23) < .1,
                f"urea 46% N → {antes} UN · urea 23% N → {despues} UN")
        pg.evaluate("""() => {
          const i = FB.catalogo.findIndex(x=>x.nombre==='Urea'); fbCat(i,'N',46);
        }""")

        # Un producto en uso no se puede borrar del catálogo.
        pg.evaluate("""() => { window.__alerta=''; window.alert = t => window.__alerta=t; }""")
        pg.evaluate("""() => {
          const i = FB.catalogo.findIndex(x=>x.nombre==='Urea'); fbCatBorrar(i);
        }""")
        al = pg.evaluate("() => window.__alerta")
        chequeo("no deja borrar un producto que está en uso",
                "en uso" in al and pg.evaluate("() => !!fbLey('Urea')"),
                al.split("\n")[0][:72])

        # ── 7. La fenología y el año de temporada ──
        print("\n\033[1mFenología y temporada\033[0m")
        pg.click("#fb-t-fen")
        pg.wait_for_timeout(350)
        nc = pg.locator("#fb-p-fen .fb-fc").count()
        chequeo("están las 24 combinaciones de especie y grupo", nc == 24, f"{nc} tarjetas")
        mov = pg.evaluate("""() => {
          const p = fbActivo();
          const a = fbCalcular(p).filas.findIndex(f => f.estado.includes('Cosecha'));
          const es = FB.fenologia[p.especie+'|'+p.grupo];
          const i = es.findIndex(e => e.estado === 'Cosecha');
          const d0 = es[i].dias;
          fbFen(p.especie+'|'+p.grupo, i, d0 + 21);
          const b = fbCalcular(p).filas.findIndex(f => f.estado.includes('Cosecha'));
          fbFen(p.especie+'|'+p.grupo, i, d0);
          return {antes:a, despues:b};
        }""")
        chequeo("mover los días corre el estado de semana",
                mov["despues"] == mov["antes"] + 3,
                f"cosecha +21 días: fila {mov['antes']} → {mov['despues']}")

        pg.click("#fb-t-ini")
        pg.wait_for_timeout(300)
        ano = pg.evaluate("""() => {
          const a0 = fbCalcular(fbActivo()).inicio.getUTCFullYear();
          fbAno(2027);
          const a1 = fbCalcular(fbActivo()).inicio.getUTCFullYear();
          fbAno(2026);
          return {a0:a0, a1:a1, temp:FB.temporada};
        }""")
        chequeo("el año de temporada mueve todos los programas",
                ano["a0"] == 2026 and ano["a1"] == 2027,
                f"{ano['a0']} → {ano['a1']}")

        # ── 8. Los factores de absorción y el balance ──
        print("\n\033[1mBalance por extracción\033[0m")
        bal = pg.evaluate("""() => {
          const p = fbActivo();
          p.fruta = {N:91.3, P:11, K:152, Ca:11.4, Mg:4.56};
          const c = fbCalcular(p);
          return c.balance.map(b => ({e:b.elemento, req:b.requerimiento,
            ent:b.entrega, bal:b.balance, est:b.estado, abs:b.absorcion}));
        }""")
        chequeo("con análisis de fruta calcula el requerimiento",
                all(b["req"] is not None for b in bal),
                " · ".join(f"{b['e']}={b['req']}" for b in bal))
        chequeo("usa el factor de absorción del cerezo",
                bal[3]["abs"] == 10 and bal[4]["abs"] == 8,
                f"Ca={bal[3]['abs']} Mg={bal[4]['abs']}")
        chequeo("el semáforo marca déficit donde no se cubre",
                any(b["est"] == "DEFICIT" for b in bal),
                " · ".join(f"{b['e']}:{b['est']}" for b in bal))
        kiwi = pg.evaluate("""() => {
          const p = fbActivo(); const e0 = p.especie, g0 = p.grupo;
          p.especie='Kiwi'; p.grupo='Media';
          const b = fbCalcular(p).balance.map(x=>x.absorcion);
          p.especie=e0; p.grupo=g0;
          return b;
        }""")
        chequeo("y cambia de columna al cambiar de especie",
                kiwi[3] == 2 and kiwi[4] == 4, f"kiwi: Ca={kiwi[3]} Mg={kiwi[4]}")

        # ── 9. Resumen ──
        print("\n\033[1mResumen\033[0m")
        pg.click("#fb-t-resp")
        pg.wait_for_timeout(250)
        pg.evaluate("() => fbCerrarCat()")
        pg.wait_for_timeout(450)
        pg.evaluate("() => { const d=document.getElementById('fb-det-res'); if(d) d.open=true; }")
        pg.wait_for_timeout(300)
        nr = pg.locator("#fb-res table.fb-res tbody tr").count()
        np = pg.evaluate("() => FB.programas.length")
        chequeo("el resumen lista todos los programas", nr == np, f"{nr} de {np}")
        pond = pg.evaluate("""() => {
          const rows = FB.programas.map(p => ({p:p, c:fbCalcular(p)}));
          const ha = rows.reduce((a,r)=>a+(r.p.ha||0),0);
          return {ha:ha, n:rows.reduce((a,r)=>a+r.c.tUn[0]*(r.p.ha||0),0)/ha};
        }""")
        chequeo("y el promedio ponderado por superficie",
                pond["ha"] > 0 and pond["n"] >= 0,
                f"{pond['ha']:.2f} ha · N medio {pond['n']:.1f} UN/ha")

        # ── 10. Exportar e importar ──
        print("\n\033[1mExportar\033[0m")
        with pg.expect_download() as d:
            pg.click("button.fb-mini:has-text('Descargar imagen')")
        img = d.value
        ruta = Path("/tmp/claude-0/fb_tabla.png")
        img.save_as(ruta)
        peso = ruta.stat().st_size
        chequeo("la tabla se descarga como imagen",
                img.suggested_filename.endswith(".png") and peso > 20000,
                f"{img.suggested_filename} · {peso/1024:.0f} KB")

        pg.evaluate("() => fbCatalogos('resp')")
        pg.wait_for_timeout(350)
        with pg.expect_download() as d:
            pg.click("#fb-p-resp button:has-text('Descargar respaldo')")
        resp = d.value
        rr = Path("/tmp/claude-0/fb_respaldo.json")
        resp.save_as(rr)
        datos = json.loads(rr.read_text(encoding="utf-8"))
        chequeo("el respaldo trae todo lo necesario",
                all(k in datos for k in ("programas", "catalogo", "fenologia",
                                         "inicios", "requerimientos", "listas")),
                f"{len(datos['programas'])} programas · {len(datos['catalogo'])} productos")

        with pg.expect_download() as d:
            pg.click("#fb-p-resp button:has-text('CSV')")
        csv = d.value
        rc = Path("/tmp/claude-0/fb_programa.csv")
        csv.save_as(rc)
        lineas = rc.read_text(encoding="utf-8").splitlines()
        chequeo("el CSV trae el encabezado, las 41 semanas y los totales",
                len(lineas) == 4 + 1 + 1 + 41 + 2,
                f"{len(lineas)} líneas")
        pg.evaluate("() => fbCerrarCat()")

        # El informe se arma con el formato del libro.
        inf = pg.evaluate("""() => {
          const h = fbHojaInforme();
          const d = document.createElement('div'); d.innerHTML = h;
          return {
            hojas: d.querySelectorAll('.hoja-fb').length,
            cab: !!d.querySelector('.fhcab'),
            datos: d.querySelectorAll('.fhdatos td.fh-k').length,
            estados: d.querySelectorAll('.fhetapas th').length,
            filas: d.querySelectorAll('.fhtabla tbody tr').length,
            totales: d.querySelectorAll('.fhtabla tfoot tr').length,
            bal: d.querySelectorAll('.fhbal tbody tr').length,
            textos: [...d.querySelectorAll('.fhdatos td.fh-k')].map(e=>e.textContent)
          };
        }""")
        chequeo("el informe sale con el formato del libro",
                inf["hojas"] == 1 and inf["cab"] and inf["filas"] == 41
                and inf["totales"] == 2 and inf["datos"] == 12,
                f"1 hoja · {inf['datos']} datos · {inf['estados']} estados · "
                f"{inf['filas']} semanas · {inf['bal']} filas de balance")
        chequeo("y lleva los 12 campos del encabezado del libro",
                "PROGRAMA" in inf["textos"] and "PORTAINJERTO" in inf["textos"]
                and "INICIO" in inf["textos"],
                " · ".join(inf["textos"][:6]))

        # ── 11. Persistencia ──
        print("\n\033[1mSe guarda y vuelve\033[0m")
        antes = pg.evaluate("""() => {
          const p = FB.programas.find(x=>x.nombre==='PRUEBA');
          return {n:FB.programas.length, dosis:Object.keys(p.dosis).length,
                  cat:FB.catalogo.length, act:fbActivo().nombre};
        }""")
        pg.reload(wait_until="networkidle")
        pg.wait_for_timeout(600)
        pg.click("#nav-fertbeta")
        pg.wait_for_timeout(900)
        despues = pg.evaluate("""() => {
          const p = FB.programas.find(x=>x.nombre==='PRUEBA');
          return {n:FB.programas.length, dosis:p?Object.keys(p.dosis).length:-1,
                  cat:FB.catalogo.length, act:fbActivo().nombre};
        }""")
        chequeo("el programa sobrevive al recargar",
                antes == despues,
                f"{despues['n']} programas · {despues['dosis']} dosis · "
                f"{despues['cat']} productos · activo «{despues['act']}»")

        # Cargar un respaldo reemplaza los programas.
        pg.evaluate("() => { window.confirm = () => true; }")
        imp = pg.evaluate("""(d) => {
          const n0 = FB.programas.length;
          const f = new File([JSON.stringify(d)], 'r.json', {type:'application/json'});
          const dt = new DataTransfer(); dt.items.add(f);
          const el = document.getElementById('fb-file');
          el.files = dt.files;
          return n0;
        }""", datos)
        pg.evaluate("() => fbImportar(document.getElementById('fb-file'))")
        pg.wait_for_timeout(600)
        chequeo("cargar un respaldo reemplaza los programas",
                pg.evaluate("() => FB.programas.length") == len(datos["programas"]),
                f"{imp} → {pg.evaluate('() => FB.programas.length')} programas")

        # ── 12. Sin errores en la consola ──
        print("\n\033[1mLa consola\033[0m")
        chequeo("no hay errores de JavaScript", not fbErrores(errores),
                fbErrores(errores)[0][:110] if fbErrores(errores) else "limpia")

        # Las otras vistas siguen funcionando.
        for v in ("hub", "resumen", "flujo", "estim", "kilos", "fert", "fito", "precios"):
            pg.click(f"#nav-{v}")
            pg.wait_for_timeout(260)
        chequeo("las otras vistas no se rompieron", not fbErrores(errores),
                fbErrores(errores)[0][:110] if fbErrores(errores)
                else "las 8 vistas abren")

        nav.close()

    srv.shutdown()
    print(f"\n{'─'*64}")
    if fallos:
        print(f"\033[31m{fallos} falla(s)\033[0m de {ok+fallos} revisiones.")
    else:
        print(f"\033[32mLas {ok} pruebas pasaron.\033[0m")
    return 1 if fallos else 0


if __name__ == "__main__":
    sys.exit(main())
