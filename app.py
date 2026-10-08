from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    send_from_directory,
    abort
)

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import simpleSplit
from datetime import datetime, date, timedelta, timezone
from functools import wraps
import calendar
import json
import os
import re
import shutil
import uuid

app = Flask(__name__)
# En Render conviene definir SECRET_KEY como variable de entorno.
app.secret_key = os.environ.get("SECRET_KEY", "DALMA FRANCO")

# --------------------------------
# CARPETAS
# --------------------------------
# Por defecto todo se guarda junto al proyecto (como antes).
# Si en Render agregás un disco persistente, definí DATA_DIR con su ruta
# (ej: /var/data) y los datos sobreviven a cada actualización.

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.environ.get("DATA_DIR", BASE_DIR)
os.makedirs(DATA_DIR, exist_ok=True)

PEDIDOS_DIR = os.path.join(DATA_DIR, "pedidos")
os.makedirs(PEDIDOS_DIR, exist_ok=True)

# Argentina no tiene horario de verano: UTC-3 fijo.
ZONA_AR = timezone(timedelta(hours=-3))


def ahora():
    return datetime.now(ZONA_AR)


def hoy():
    return ahora().date()


# --------------------------------
# LECTURA / ESCRITURA DE JSON
# --------------------------------

def ruta(nombre):
    return os.path.join(DATA_DIR, nombre)


def abrir_json(camino):
    """Lee un JSON probando UTF-8 y, si falla, la codificación de Windows."""
    for codificacion in ("utf-8-sig", "cp1252"):
        try:
            with open(camino, encoding=codificacion) as archivo:
                return json.load(archivo)
        except UnicodeDecodeError:
            continue
    raise ValueError("No se pudo leer " + camino)


def leer_json(nombre, defecto):
    try:
        return abrir_json(ruta(nombre))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return defecto


def guardar_json(nombre, datos):
    with open(ruta(nombre), "w", encoding="utf-8") as archivo:
        json.dump(datos, archivo, ensure_ascii=False, indent=2)


# --------------------------------
# NOTAS DEL DÍA (se imprimen en el PDF, una vez por pedido)
# Son los valores iniciales: después se editan desde el panel
# de administradora (Hoja de pedido).
# --------------------------------

DIAS = ["LUNES", "MARTES", "MIÉRCOLES", "JUEVES", "VIERNES", "SÁBADO", "DOMINGO"]

NOTAS_DEFECTO = {
    "LUNES": "Hoy toca: Lunes - Airbag\n\nMientras más me apuren...\nmás me voy a tardar. 😂",

    "MARTES": "Sabemos que cada pedido refleja el esfuerzo de todo el equipo.\n"
              "¡Gracias por dar lo mejor de ustedes!\n"
              "¡Buena jornada!",

    "MIÉRCOLES": "\"Despacio, que estoy apurada.\"\n"
                 "¡Ya estamos en mitad de semana!",

    "JUEVES": "Nunca es tarde para aprender algo nuevo.\n\n"
              "Vocabulario:\n"
              "• Envasado → con V\n"
              "PARA TENER EN CUENTA!!!!:\n"
              "Revisar 25 veces las bandejas, mirarme fijo o respirar al lado mío\n"
              "no acelera la preparación de los pedidos.\n\n"
              "PD:¡Que nunca falten los mates!",

    "VIERNES": "Después de toda una semana de trabajo...\n"
               "por fin llegamos a juntar para el asado.\n\n"
               "¡QUE TENGAN UN BENDECIDO DIA!",

    "SÁBADO": "¡Sábado 1 de Agosto!\n\n"
              "Dia del TÉ de ruda para arrancar el mes con salud,suerte y buenas energias.\n\n"
              "Que no falten las facturitas.\n\n"
              "Buen fin de semana ♡"
}

CONFIG_DEFECTO = {"encabezado": "★ DALMA FRANCO ★"}

# --------------------------------
# CREAR ARCHIVOS SI NO EXISTEN
# (si ya existen en el proyecto, se copian tal cual a DATA_DIR)
# --------------------------------

def inicializar(nombre, defecto):
    destino = ruta(nombre)
    if os.path.exists(destino):
        return
    origen = os.path.join(BASE_DIR, nombre)
    if os.path.exists(origen) and os.path.abspath(origen) != os.path.abspath(destino):
        shutil.copyfile(origen, destino)
    else:
        guardar_json(nombre, defecto)


inicializar("productos.json", [
    {"codigo": "1001", "nombre": "Ravioles Ricota"},
    {"codigo": "1002", "nombre": "Ñoquis"},
    {"codigo": "1003", "nombre": "Tallarines"}
])
# Solo se usa si no existe usuarios.json: cambiá las claves apenas entres.
inicializar("usuarios.json", {"Dalma": "cambiar-esta-clave", "Walter": "cambiar-esta-clave"})
inicializar("notas.json", NOTAS_DEFECTO)
inicializar("config.json", CONFIG_DEFECTO)
inicializar("eventos.json", [])

# --------------------------------
# ROLES Y PERMISOS
# --------------------------------
# La administradora es el usuario "Dalma" (sin importar mayúsculas).

def es_admin():
    return session.get("usuario", "").lower() == "dalma"


def login_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if "usuario" not in session:
            return redirect("/")
        return f(*args, **kwargs)
    return envoltura


def admin_requerido(f):
    @wraps(f)
    def envoltura(*args, **kwargs):
        if "usuario" not in session:
            return redirect("/")
        if not es_admin():
            return redirect("/pedido")
        return f(*args, **kwargs)
    return envoltura


# --------------------------------
# PEDIDOS GUARDADOS: AYUDAS
# --------------------------------

def id_valido(pid):
    return bool(re.fullmatch(r"Pedido_[\d\-_]+", pid or ""))


def cargar_pedido(pid):
    if not id_valido(pid):
        return None
    try:
        return abrir_json(os.path.join(PEDIDOS_DIR, pid + ".json"))
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None


def puede_ver(pedido):
    if es_admin():
        return True
    # Lo ve quien lo cargó y también el vendedor a cuyo nombre quedó.
    yo = session.get("usuario", "").lower()
    return yo in ((pedido.get("creado_por") or "").lower(),
                  (pedido.get("vendedor") or "").lower())


# --------------------------------
# CALENDARIO Y CARTEL DE "PASAR CANTIDADES"
# --------------------------------

MESES = ["Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio",
         "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre"]


def construir_calendario():
    hoy_ = hoy()
    try:
        anio, mes = request.args.get("mes", "").split("-")
        primero = date(int(anio), int(mes), 1)
    except ValueError:
        primero = date(hoy_.year, hoy_.month, 1)

    eventos = leer_json("eventos.json", [])
    por_dia = {}
    for e in eventos:
        por_dia.setdefault(e.get("fecha", ""), []).append(e)

    semanas = []
    for semana in calendar.Calendar(firstweekday=0).monthdatescalendar(primero.year, primero.month):
        semanas.append([
            {
                "fecha": d,
                "del_mes": d.month == primero.month,
                "hoy": d == hoy_,
                "eventos": por_dia.get(d.isoformat(), [])
            }
            for d in semana
        ])

    prefijo = primero.strftime("%Y-%m")
    eventos_mes = sorted(
        [e for e in eventos if e.get("fecha", "").startswith(prefijo)],
        key=lambda e: e["fecha"]
    )

    anterior = (primero - timedelta(days=1)).replace(day=1)
    siguiente = (primero + timedelta(days=32)).replace(day=1)

    return {
        "titulo": f"{MESES[primero.month - 1]} {primero.year}",
        "semanas": semanas,
        "eventos_mes": eventos_mes,
        "prev": anterior.strftime("%Y-%m"),
        "sig": siguiente.strftime("%Y-%m")
    }


def carteles_pendientes():
    """Eventos a 7 días o menos (o ya vencidos) cuyas cantidades no se pasaron."""
    hoy_ = hoy()
    resultado = []
    for e in leer_json("eventos.json", []):
        if e.get("cantidades_pasadas"):
            continue
        try:
            dias = (date.fromisoformat(e["fecha"]) - hoy_).days
        except (KeyError, ValueError):
            continue
        if dias <= 7:
            resultado.append({**e, "dias": dias})
    resultado.sort(key=lambda e: e["fecha"])
    return resultado


@app.context_processor
def inyectar():
    return dict(
        es_admin=es_admin(),
        usuario=session.get("usuario", ""),
        fecha_actual=ahora().strftime("%d/%m/%Y - %H:%M"),
        calendario=construir_calendario,
        carteles=carteles_pendientes
    )


def volver_a(por_defecto):
    destino = request.form.get("volver", "")
    if destino.startswith("/") and not destino.startswith("//"):
        return destino
    return por_defecto


@app.route("/calendario/agregar", methods=["POST"])
@login_requerido
def calendario_agregar():
    fecha = request.form.get("fecha", "").strip()
    titulo = request.form.get("titulo", "").strip()
    try:
        date.fromisoformat(fecha)
    except ValueError:
        return redirect(volver_a("/pedido"))
    if titulo:
        eventos = leer_json("eventos.json", [])
        eventos.append({
            "id": uuid.uuid4().hex[:8],
            "fecha": fecha,
            "titulo": titulo[:80],
            "creado_por": session["usuario"],
            "cantidades_pasadas": False
        })
        guardar_json("eventos.json", eventos)
    return redirect(volver_a("/pedido"))


@app.route("/calendario/<eid>/cantidades", methods=["POST"])
@login_requerido
def calendario_cantidades(eid):
    eventos = leer_json("eventos.json", [])
    for e in eventos:
        if e.get("id") == eid:
            e["cantidades_pasadas"] = True
            e["pasadas_por"] = session["usuario"]
    guardar_json("eventos.json", eventos)
    return redirect(volver_a("/pedido"))


@app.route("/calendario/<eid>/borrar", methods=["POST"])
@login_requerido
def calendario_borrar(eid):
    eventos = leer_json("eventos.json", [])
    nuevos = [
        e for e in eventos
        if not (e.get("id") == eid and (es_admin() or e.get("creado_por") == session["usuario"]))
    ]
    guardar_json("eventos.json", nuevos)
    return redirect(volver_a("/pedido"))


# --------------------------------
# LOGIN
# --------------------------------

@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        usuario = request.form.get("usuario", "").strip()
        password = request.form.get("password", "")
        usuarios = leer_json("usuarios.json", {})
        if usuario in usuarios and usuarios[usuario] == password:
            session["usuario"] = usuario
            return redirect("/admin" if es_admin() else "/pedido")
        error = "Usuario o contraseña incorrectos"
    return render_template("login.html", error=error)


# --------------------------------
# PEDIDO (vendedor y administradora)
# --------------------------------

@app.route("/pedido")
@login_requerido
def pedido():
    return render_template(
        "pedido.html",
        productos=leer_json("productos.json", []),
        vendedores=list(leer_json("usuarios.json", {}).keys()),
        edit=None
    )


@app.route("/pedido/<pid>/editar")
@admin_requerido
def editar_pedido(pid):
    p = cargar_pedido(pid)
    if not p or not p.get("items"):
        return redirect("/pedidos")
    p["id"] = pid
    return render_template(
        "pedido.html",
        productos=leer_json("productos.json", []),
        vendedores=list(leer_json("usuarios.json", {}).keys()),
        edit=p
    )


# --------------------------------
# GENERAR PDF
# --------------------------------

def dibujar_logo(pdf, x, y, lado=46):
    """Logo: cuadrado rosa con 'DF' y una chispa dorada."""
    pdf.setFillColorRGB(0.83, 0.33, 0.49)
    pdf.setStrokeColorRGB(0.60, 0.21, 0.34)
    pdf.setLineWidth(1)
    pdf.roundRect(x, y, lado, lado, 11, fill=1, stroke=1)

    pdf.setFillColorRGB(0.98, 0.92, 0.94)
    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawCentredString(x + lado / 2, y + 15, "DF")

    # Chispa dorada arriba a la derecha
    cx, cy = x + lado - 8, y + lado - 8
    R, r = 8, 2.4
    p = pdf.beginPath()
    p.moveTo(cx, cy + R)
    p.lineTo(cx + r, cy + r)
    p.lineTo(cx + R, cy)
    p.lineTo(cx + r, cy - r)
    p.lineTo(cx, cy - R)
    p.lineTo(cx - r, cy - r)
    p.lineTo(cx - R, cy)
    p.lineTo(cx - r, cy + r)
    p.close()
    pdf.setFillColorRGB(0.94, 0.62, 0.15)
    pdf.drawPath(p, fill=1, stroke=0)

    pdf.setStrokeColorRGB(0, 0, 0)
    pdf.setFillColorRGB(0, 0, 0)


def ajustar(pdf, texto, fuente, tam, ancho_max):
    """Recorta el texto con '…' si no entra en el ancho disponible."""
    texto = str(texto or "")
    if pdf.stringWidth(texto, fuente, tam) <= ancho_max:
        return texto
    while texto and pdf.stringWidth(texto + "...", fuente, tam) > ancho_max:
        texto = texto[:-1]
    return texto + "..."


@app.route("/generar", methods=["POST"])
@login_requerido
def generar():

    cliente       = request.form["cliente"]
    razon         = request.form.get("razon", "")
    zona          = request.form.get("zona", "")
    fecha_entrega = request.form["fecha_entrega"]
    nota          = request.form.get("nota", "")

    # El vendedor es quien está logueado; la administradora puede elegir.
    if es_admin():
        vendedor = request.form.get("vendedor") or session["usuario"]
    else:
        vendedor = session["usuario"]

    productos_form  = request.form.getlist("producto[]")
    cantidades_form = request.form.getlist("cantidad[]")

    # Si viene pedido_id (solo administradora) se reemplaza ese pedido.
    pedido_id = request.form.get("pedido_id", "")
    previo = cargar_pedido(pedido_id) if (pedido_id and es_admin()) else None

    if previo is not None:
        nombre_pdf = pedido_id + ".pdf"
        creado_por = previo.get("creado_por") or previo.get("vendedor") or vendedor
    else:
        nombre_pdf = f"Pedido_{ahora().strftime('%d-%m-%Y_%H-%M-%S')}.pdf"
        creado_por = session["usuario"]

    # Día en español
    dias_es = {
        "Monday": "LUNES", "Tuesday": "MARTES", "Wednesday": "MIÉRCOLES",
        "Thursday": "JUEVES", "Friday": "VIERNES",
        "Saturday": "SÁBADO", "Sunday": "DOMINGO"
    }
    try:
        fe = datetime.strptime(fecha_entrega, "%Y-%m-%d")
        dia_semana        = dias_es.get(fe.strftime("%A"), "")
        fecha_entrega_fmt = fe.strftime("%d / %m / %Y")
    except Exception:
        dia_semana        = ""
        fecha_entrega_fmt = fecha_entrega

    fecha_envio = ahora().strftime("%d/%m/%Y %H:%M")

    notas_dia = leer_json("notas.json", NOTAS_DEFECTO)

    ruta_pdf = os.path.join(PEDIDOS_DIR, nombre_pdf)

    # ── TAMAÑO A4 ──
    ancho, alto = A4   # 595 x 842 puntos

    # Columnas de la tabla de productos
    X_IZQ, X_DER = 30, ancho - 30          # 30 .. 565
    X_PROD = 105                           # inicio del nombre del producto
    CANT_X0, CANT_X1 = 395, 470            # cuadrito de cantidad
    LOTE_X0, LOTE_X1 = 480, 560            # cuadrito de lote

    pdf = canvas.Canvas(ruta_pdf, pagesize=A4)

    def dibujar_nota_dia(pdf, y_inicio):
        """Dibuja la nota del día, centrada, debajo del título. Devuelve el nuevo y."""
        texto = notas_dia.get(dia_semana, "")
        if not texto:
            return y_inicio

        pdf.setFont("Helvetica-BoldOblique", 8)
        pdf.setFillColorRGB(0.35, 0.35, 0.35)

        y = y_inicio
        for linea in texto.split("\n"):
            if linea.strip() == "":
                y -= 6
                continue
            pdf.drawCentredString(ancho / 2, y, linea)
            y -= 10

        pdf.setFillColorRGB(0, 0, 0)
        return y - 4

    def celda(x, y_top, w, h, etiqueta, valor, tam=11, fondo=None, color=(0, 0, 0)):
        """Una celda con borde, etiqueta chica arriba y valor abajo."""
        if fondo:
            pdf.setFillColorRGB(*fondo)
            pdf.rect(x, y_top - h, w, h, fill=1, stroke=0)
        pdf.setStrokeColorRGB(0.5, 0.5, 0.5)
        pdf.setLineWidth(0.8)
        pdf.rect(x, y_top - h, w, h, fill=0, stroke=1)
        pdf.setFillColorRGB(0.35, 0.35, 0.35)
        pdf.setFont("Helvetica", 7)
        pdf.drawString(x + 8, y_top - 11, etiqueta)
        pdf.setFillColorRGB(*color)
        pdf.setFont("Helvetica-Bold", tam)
        pdf.drawString(x + 8, y_top - 26, ajustar(pdf, valor, "Helvetica-Bold", tam, w - 16) or " ")
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setLineWidth(1)

    def nueva_pagina(pdf, primera=False):
        """Dibuja el marco y encabezado en cada página."""
        pdf.setLineWidth(1)
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.rect(20, 20, ancho - 40, alto - 40)

        # Encabezado: logo + nombre
        dibujar_logo(pdf, 35, alto - 92)

        pdf.setFillColorRGB(0.73, 0.46, 0.09)
        pdf.setFont("Helvetica-Bold", 22)
        pdf.drawString(92, alto - 62, "Dalma Franco")

        pdf.setFillColorRGB(0.37, 0.37, 0.35)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(93, alto - 78, "NOTA DE PEDIDO")
        pdf.setFillColorRGB(0, 0, 0)

        # Línea bajo encabezado
        pdf.setLineWidth(1.5)
        pdf.line(20, alto - 100, ancho - 20, alto - 100)
        pdf.setLineWidth(1)

        # En las hojas siguientes la tabla arranca justo debajo del encabezado
        tabla_y = alto - 130

        if primera:
            # Nota del día (una sola vez, debajo del encabezado)
            y_nota = dibujar_nota_dia(pdf, alto - 114)

            # ── CUADRO DE DATOS ──
            ancho_cuadro = X_DER - X_IZQ
            mitad = ancho_cuadro / 2
            alto_fila = 34
            top = y_nota - 6

            celda(X_IZQ, top, mitad, alto_fila, "CLIENTE", cliente)
            celda(X_IZQ + mitad, top, mitad, alto_fila, "RAZÓN SOCIAL", razon)

            top2 = top - alto_fila
            celda(X_IZQ, top2, mitad, alto_fila, "ZONA", zona)
            celda(X_IZQ + mitad, top2, mitad, alto_fila, "VENDEDOR", vendedor)

            top3 = top2 - alto_fila
            celda(X_IZQ, top3, mitad, alto_fila, "FECHA DE PEDIDO", fecha_envio)
            entrega = (dia_semana + "  " + fecha_entrega_fmt).strip()
            celda(X_IZQ + mitad, top3, mitad, alto_fila, "FECHA DE ENTREGA", entrega,
                  fondo=(0.98, 0.93, 0.85), color=(0.52, 0.31, 0.04))

            # NOTA (ocupa todo el ancho y crece si el texto es largo)
            top4 = top3 - alto_fila
            lineas_nota = []
            for parte in (nota or "").split("\n"):
                lineas_nota += simpleSplit(parte or " ", "Helvetica", 10, ancho_cuadro - 16)
            lineas_nota = lineas_nota[:6]
            alto_nota = max(40, 22 + 12 * len(lineas_nota))

            pdf.setStrokeColorRGB(0.5, 0.5, 0.5)
            pdf.setLineWidth(0.8)
            pdf.rect(X_IZQ, top4 - alto_nota, ancho_cuadro, alto_nota, fill=0, stroke=1)
            pdf.setFillColorRGB(0.35, 0.35, 0.35)
            pdf.setFont("Helvetica", 7)
            pdf.drawString(X_IZQ + 8, top4 - 11, "NOTA")
            pdf.setFillColorRGB(0, 0, 0)
            pdf.setFont("Helvetica", 10)
            for i, linea in enumerate(lineas_nota):
                pdf.drawString(X_IZQ + 8, top4 - 25 - 12 * i, linea)
            pdf.setStrokeColorRGB(0, 0, 0)
            pdf.setLineWidth(1)

            tabla_y = top4 - alto_nota - 31

        return tabla_y

    def dibujar_cabecera_tabla(pdf, y):
        """Dibuja el encabezado de la tabla de productos."""
        pdf.setFillColorRGB(0.60, 0.21, 0.34)
        pdf.rect(X_IZQ, y - 5, X_DER - X_IZQ, 22, fill=1, stroke=0)
        pdf.setFillColorRGB(0.98, 0.92, 0.94)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(40, y + 3, "CÓDIGO")
        pdf.drawString(X_PROD, y + 3, "PRODUCTO")
        pdf.drawCentredString((CANT_X0 + CANT_X1) / 2, y + 3, "CANTIDAD")
        pdf.drawCentredString((LOTE_X0 + LOTE_X1) / 2, y + 3, "LOTE")
        pdf.setFillColorRGB(0, 0, 0)
        return y - 27

    # Primera página
    y = nueva_pagina(pdf, primera=True)
    y = dibujar_cabecera_tabla(pdf, y)

    detalle_wa = ""
    items = []
    MARGEN_INF = 50   # espacio mínimo al pie antes de nueva página
    ALTO_FILA  = 27

    pdf.setFillColorRGB(0, 0, 0)

    for idx, (producto, cantidad) in enumerate(zip(productos_form, cantidades_form)):

        # Nueva página si no hay espacio
        if y - ALTO_FILA < MARGEN_INF:
            pdf.showPage()
            y = nueva_pagina(pdf, primera=False)
            y = dibujar_cabecera_tabla(pdf, y)
            pdf.setFillColorRGB(0, 0, 0)

        if " - " in producto:
            partes = producto.split(" - ", 1)
            codigo          = partes[0]
            nombre_producto = partes[1]
        else:
            codigo          = "-"
            nombre_producto = producto

        # Fila: fondo alternado y borde gris
        if idx % 2 == 1:
            pdf.setFillColorRGB(0.95, 0.94, 0.91)
            pdf.rect(X_IZQ, y - 5, X_DER - X_IZQ, 22, fill=1, stroke=0)
        pdf.setStrokeColorRGB(0.7, 0.7, 0.7)
        pdf.setLineWidth(1)
        pdf.rect(X_IZQ, y - 5, X_DER - X_IZQ, 22, fill=0, stroke=1)

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40, y + 5, ajustar(pdf, codigo, "Helvetica", 9, 55))

        pdf.setFont("Helvetica", 10)
        pdf.drawString(X_PROD, y + 5,
                       ajustar(pdf, nombre_producto, "Helvetica", 10, CANT_X0 - X_PROD - 10))

        # Cuadritos de cantidad y de lote
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.setLineWidth(1)
        pdf.rect(CANT_X0, y - 3, CANT_X1 - CANT_X0, 18, fill=0, stroke=1)
        pdf.rect(LOTE_X0, y - 3, LOTE_X1 - LOTE_X0, 18, fill=0, stroke=1)

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawCentredString((CANT_X0 + CANT_X1) / 2, y + 2, str(cantidad))

        # Lote vacío (se completa a mano)
        y -= ALTO_FILA
        detalle_wa += f"  • {nombre_producto} x{cantidad}\n"
        items.append({"producto": producto, "cantidad": cantidad})

    pdf.save()

    # Guardar JSON (el pedido queda guardado para volver a verlo)
    datos = {
        "id":                nombre_pdf[:-4],
        "vendedor":          vendedor,
        "creado_por":        creado_por,
        "cliente":           cliente,
        "razon":             razon,
        "zona":              zona,
        "fecha_entrega":     fecha_entrega_fmt,
        "fecha_entrega_iso": fecha_entrega,
        "nota":              nota,
        "items":             items,
        "detalle_productos": detalle_wa,
        "pdf":               nombre_pdf,
        "fecha_envio":       fecha_envio
    }
    if previo is not None:
        datos["editado"] = True

    with open(os.path.join(PEDIDOS_DIR, nombre_pdf[:-4] + ".json"), "w", encoding="utf-8") as f:
        json.dump(datos, f, ensure_ascii=False, indent=2)

    return redirect(f"/ver_pdf/{nombre_pdf}")


# --------------------------------
# VER PDF
# --------------------------------

@app.route("/ver_pdf/<nombre>")
@login_requerido
def ver_pdf(nombre):
    pid = nombre[:-4] if nombre.endswith(".pdf") else nombre
    if not id_valido(pid):
        abort(404)
    pedido = cargar_pedido(pid)
    if pedido is None:
        if not es_admin():
            abort(404)
        pedido = {}
    elif not puede_ver(pedido):
        abort(403)
    return render_template("ver_pdf.html", nombre=pid + ".pdf", pedido=pedido)


# --------------------------------
# DESCARGAR PDF
# --------------------------------

@app.route("/pdf/<nombre>")
@login_requerido
def pdf_archivo(nombre):
    pid = nombre[:-4] if nombre.endswith(".pdf") else nombre
    if not id_valido(pid):
        abort(404)
    pedido = cargar_pedido(pid)
    if pedido is None:
        if not es_admin():
            abort(404)
    elif not puede_ver(pedido):
        abort(403)
    return send_from_directory(directory=PEDIDOS_DIR, path=pid + ".pdf", as_attachment=True)


# --------------------------------
# PEDIDOS GUARDADOS
# Vendedor: solo los suyos. Administradora: todos.
# --------------------------------

@app.route("/pedidos")
@login_requerido
def ver_pedidos():
    lista = []
    for archivo in os.listdir(PEDIDOS_DIR):
        if not archivo.endswith(".json"):
            continue
        camino = os.path.join(PEDIDOS_DIR, archivo)
        try:
            p = abrir_json(camino)
        except (json.JSONDecodeError, ValueError, OSError):
            continue
        if not isinstance(p, dict):
            continue
        p.setdefault("id", archivo[:-5])
        p.setdefault("pdf", p["id"] + ".pdf")
        if puede_ver(p):
            lista.append((os.path.getmtime(camino), p))
    lista.sort(key=lambda x: x[0], reverse=True)
    return render_template("pedidos.html", lista=[p for _, p in lista])


@app.route("/pedidos/<pid>/borrar", methods=["POST"])
@admin_requerido
def borrar_pedido(pid):
    if id_valido(pid):
        for extension in (".json", ".pdf"):
            try:
                os.remove(os.path.join(PEDIDOS_DIR, pid + extension))
            except FileNotFoundError:
                pass
    return redirect("/pedidos")


# --------------------------------
# PANEL DE ADMINISTRADORA
# --------------------------------

@app.route("/admin")
@admin_requerido
def admin():
    return render_template("admin.html", seccion="inicio")


# ---- Productos ----

@app.route("/admin/productos")
@admin_requerido
def admin_productos():
    return render_template(
        "admin.html",
        seccion="productos",
        productos=leer_json("productos.json", [])
    )


@app.route("/admin/productos/agregar", methods=["POST"])
@admin_requerido
def admin_producto_agregar():
    codigo = request.form.get("codigo", "").strip()
    nombre = request.form.get("nombre", "").strip()
    if codigo and nombre:
        productos = leer_json("productos.json", [])
        productos.append({"codigo": codigo, "nombre": nombre})
        guardar_json("productos.json", productos)
    return redirect("/admin/productos?ok=1")


@app.route("/admin/productos/<int:i>/guardar", methods=["POST"])
@admin_requerido
def admin_producto_guardar(i):
    productos = leer_json("productos.json", [])
    codigo = request.form.get("codigo", "").strip()
    nombre = request.form.get("nombre", "").strip()
    if 0 <= i < len(productos) and codigo and nombre:
        productos[i]["codigo"] = codigo
        productos[i]["nombre"] = nombre
        guardar_json("productos.json", productos)
    return redirect("/admin/productos?ok=1")


@app.route("/admin/productos/<int:i>/borrar", methods=["POST"])
@admin_requerido
def admin_producto_borrar(i):
    productos = leer_json("productos.json", [])
    if 0 <= i < len(productos):
        productos.pop(i)
        guardar_json("productos.json", productos)
    return redirect("/admin/productos?ok=1")


# Ruta vieja: ahora se agrega desde el panel
@app.route("/agregar_producto", methods=["GET", "POST"])
@admin_requerido
def agregar_producto():
    return redirect("/admin/productos")


# ---- Hoja de pedido (encabezado y frases del día) ----

@app.route("/admin/hoja", methods=["GET", "POST"])
@admin_requerido
def admin_hoja():
    if request.method == "POST":
        cfg = leer_json("config.json", CONFIG_DEFECTO)
        cfg["encabezado"] = request.form.get("encabezado", "").strip()[:40]
        guardar_json("config.json", cfg)

        notas = {}
        for i, dia in enumerate(DIAS):
            texto = request.form.get(f"nota_{i}", "").replace("\r\n", "\n").strip()
            if texto:
                notas[dia] = texto
        guardar_json("notas.json", notas)
        return redirect("/admin/hoja?ok=1")

    return render_template(
        "admin.html",
        seccion="hoja",
        cfg=leer_json("config.json", CONFIG_DEFECTO),
        notas=leer_json("notas.json", NOTAS_DEFECTO),
        dias=DIAS
    )


# --------------------------------
# LOGOUT
# --------------------------------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# --------------------------------
# INICIAR APP
# --------------------------------

if __name__ == "__main__":
    app.run(debug=True)