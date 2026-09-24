#!/usr/bin/env python3
"""Rompe la app a propósito, de siete formas distintas, y comprueba que
la verificación lo detecte cada vez. Si una prueba no falla cuando debe,
esa revisión no sirve de nada."""

import os, re, shutil, subprocess, tempfile, json, sys

ORIG = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

def con_copia(fn):
    tmp = tempfile.mkdtemp()
    dst = os.path.join(tmp, 'sitio')
    shutil.copytree(ORIG, dst)
    try:
        fn(dst)
        p = subprocess.run([sys.executable, os.path.join(dst,'pruebas','verificar.py')],
                           capture_output=True, text=True)
        return p.returncode, p.stdout
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def w(d, n, s): open(os.path.join(d,n),'w',encoding='utf-8').write(s)
def r(d, n): return open(os.path.join(d,n),encoding='utf-8').read()

# ── las siete formas de romperla ──
def romper_sintaxis(d):
    s = r(d,'tecnica.html')
    w(d,'tecnica.html', s.replace('function saveFeno(){','function saveFeno({',1))

def romper_json(d):
    w(d,'config.json','{"off": [,]}')

def filtrar_clave(d):
    s = r(d,'tecnica.html')
    w(d,'tecnica.html', s.replace('</script>',
        'var k="AIzaSyD9xK2mNpQ7rT4vW8yB3cE6fH1jL5nP0qS";</script>',1))

def id_inexistente(d):
    s = r(d,'tecnica.html')
    w(d,'tecnica.html', s.replace('function saveFeno(){',
        'function saveFeno(){ document.getElementById("elementoQueNoExiste").focus();',1))

def boton_roto(d):
    s = r(d,'tecnica.html')
    w(d,'tecnica.html', s.replace('onclick="saveFeno()"','onclick="guardarTodoAhora()"',1))

def version_descuadrada(d):
    s = r(d,'clima.html')
    w(d,'clima.html', re.sub(r'<meta name="app-version" content="[^"]+">',
                             '<meta name="app-version" content="9.9">', s, count=1))

def estados_descuadrados(d):
    s = r(d,'tecnica.html')
    w(d,'tecnica.html', s.replace(
        'var FENO_SIGLAS=["YH","PV","BVC","RE","REx","BB","FA","CdP","CdC","FV","PaF","FCP","IP","CO"];',
        'var FENO_SIGLAS=["YH","PV","BVC","RE","REx","BB","FA"];',1))

def archivo_faltante(d):
    os.remove(os.path.join(d,'cuarteles.json'))

CASOS = [
    ('JavaScript con error de sintaxis',      romper_sintaxis,     'sintaxis'),
    ('un JSON malformado',                    romper_json,         'json'),
    ('una clave de API filtrada',             filtrar_clave,       'secretos'),
    ('un getElementById a un id inexistente', id_inexistente,      'ids'),
    ('un botón que llama a algo que no existe', boton_roto,        'onclick'),
    ('versiones que no coinciden',            version_descuadrada, 'version'),
    ('listas de estados descuadradas',        estados_descuadrados,'fenologia'),
    ('un archivo del sitio eliminado',        archivo_faltante,    'archivos'),
]

print("¿La verificación detecta errores de verdad?\n")
fallos = 0
for nombre, romper, seccion in CASOS:
    code, salida = con_copia(romper)
    detectado = code == 1 and ('[%s]' % seccion) in salida
    print("  %-44s %s" % (nombre, "detectado" if detectado else "✗ NO LO DETECTÓ"))
    if not detectado:
        fallos += 1
        print("     (código %s)" % code)
        for l in salida.splitlines():
            if 'FALLA' in l or '✗' in l: print("      ", l.strip())

print()
if fallos:
    print("%d de %d revisiones no sirven: no detectan lo que deberían." % (fallos, len(CASOS)))
    sys.exit(1)
print("Las %d revisiones detectan lo que tienen que detectar." % len(CASOS))
