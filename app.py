from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    send_from_directory
)

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4
from datetime import datetime
import json
import os

app = Flask(__name__)
app.secret_key = "DALMA FRANCO"

# --------------------------------
# CREAR ARCHIVOS SI NO EXISTEN
# --------------------------------

if not os.path.exists("productos.json"):
    productos_iniciales = [
        {"codigo": "1001", "nombre": "Ravioles Ricota"},
        {"codigo": "1002", "nombre": "Ñoquis"},
        {"codigo": "1003", "nombre": "Tallarines"}
    ]
    with open("productos.json", "w") as archivo:
        json.dump(productos_iniciales, archivo)

if not os.path.exists("usuarios.json"):
    usuarios = {"walter": "123", "ENZO" : "321"}
    with open("usuarios.json", "w") as archivo:
        json.dump(usuarios, archivo)

# --------------------------------
# LOGIN
# --------------------------------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form["usuario"]
        password = request.form["password"]
        with open("usuarios.json") as archivo:
            usuarios = json.load(archivo)
        if usuario in usuarios and usuarios[usuario] == password:
            session["usuario"] = usuario
            return redirect("/pedido")
    return render_template("login.html")

# --------------------------------
# PEDIDO
# --------------------------------

@app.route("/pedido")
def pedido():
    if "usuario" not in session:
        return redirect("/")

    with open("productos.json") as archivo:
        productos = json.load(archivo)

    fecha_actual = datetime.now().strftime("%d/%m/%Y - %H:%M")

    return render_template(
        "pedido.html",
        productos=productos,
        usuario=session["usuario"],
        fecha=fecha_actual
    )

# --------------------------------
# GENERAR PDF
# --------------------------------

@app.route("/generar", methods=["POST"])
def generar():

    cliente       = request.form["cliente"]
    razon         = request.form["razon"]
    zona          = request.form["zona"]
    vendedor      = request.form["vendedor"]
    fecha_entrega = request.form["fecha_entrega"]
    nota          = request.form["nota"]

    productos_form  = request.form.getlist("producto[]")
    cantidades_form = request.form.getlist("cantidad[]")

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

    fecha_envio = datetime.now().strftime("%d/%m/%Y %H:%M")

    if not os.path.exists("pedidos"):
        os.makedirs("pedidos")

    nombre_pdf = f"Pedido_{datetime.now().strftime('%d-%m-%Y_%H-%M')}.pdf"
    ruta       = os.path.join("pedidos", nombre_pdf)

     # ── TAMAÑO A4 ──
    ancho, alto = A4   # 595 x 842 puntos

    pdf = canvas.Canvas(ruta, pagesize=A4)

    def nueva_pagina(pdf, primera=False):
        """Dibuja el marco y encabezado en cada página."""
        pdf.setLineWidth(1)
        pdf.rect(20, 20, ancho - 40, alto - 40)

        # Encabezado
        pdf.setFont("Helvetica", 9)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(35, alto - 30, "★ DALMA FRANCO ★ ")

        pdf.setFont("Helvetica-Bold", 18)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(180, alto - 35, "NOTA DE PEDIDO")

        # Timestamp arriba derecha
        pdf.setFont("Helvetica", 7)
        pdf.setFillColorRGB(0, 0, 0)
        pdf.drawString(430, alto - 25, "Enviado")
        pdf.drawString(423, alto - 34, fecha_envio)

        # Línea bajo encabezado
        pdf.setStrokeColorRGB(0, 0, 0)
        pdf.line(20, alto - 45, ancho - 20, alto - 45)

        if primera:
            # ── CAMPOS INFO ── bien espaciados
            y0 = alto - 58

            # RAZÓN SOCIAL
            pdf.setFont("Helvetica", 8)
            pdf.setFillColorRGB(0, 0, 0)
            pdf.drawString(35, y0, "RAZÓN SOCIAL")
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(35, y0 - 13, razon if razon else " ")
            pdf.line(35, y0 - 17, 290, y0 - 17)

            # ZONA
            pdf.setFont("Helvetica", 8)
            pdf.drawString(310, y0, "ZONA")
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(310, y0 - 13, zona if zona else " ")
            pdf.line(310, y0 - 17, ancho - 25, y0 - 17)

            # VENDEDOR
            y1 = y0 - 32
            pdf.setFont("Helvetica", 8)
            pdf.drawString(35, y1, "VENDEDOR")
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(35, y1 - 14, vendedor)
            pdf.line(35, y1 - 18, 290, y1 - 18)

            # FECHA DE ENTREGA
            pdf.setFont("Helvetica", 8)
            pdf.drawString(310, y1, "FECHA DE ENTREGA")
            pdf.setFont("Helvetica-Bold", 16)
            pdf.drawString(310, y1 - 15, dia_semana)
            pdf.setFont("Helvetica-Bold", 12)
            pdf.drawString(310, y1 - 30, fecha_entrega_fmt)
            pdf.line(310, y1 - 34, ancho - 25, y1 - 34)

            # CLIENTE
            y2 = y1 - 50
            pdf.setFont("Helvetica", 8)
            pdf.drawString(35, y2, "CLIENTE")
            pdf.setFont("Helvetica-Bold", 11)
            pdf.drawString(35, y2 - 13, cliente)
            pdf.line(35, y2 - 17, 290, y2 - 17)

            # NOTA
            y3 = y2 - 32
            pdf.setFont("Helvetica", 8)
            pdf.drawString(35, y3, "NOTA")
            pdf.setFont("Helvetica", 11)
            pdf.drawString(35, y3 - 13, nota if nota else " ")
            pdf.line(35, y3 - 17, ancho - 25, y3 - 17)

            tabla_y = y3 - 32

        return tabla_y

    def dibujar_cabecera_tabla(pdf, y):
        """Dibuja el encabezado de la tabla de productos."""
        pdf.setFillColorRGB(0.1, 0.1, 0.1)
        pdf.rect(30, y - 5, ancho - 60, 22, fill=1)
        pdf.setFillColorRGB(1, 1, 1)
        pdf.setFont("Helvetica-Bold", 9)
        pdf.drawString(40,  y + 3, "CÓDIGO")
        pdf.drawString(120, y + 3, "PRODUCTO")
        pdf.drawString(370, y + 3, "CANTIDAD")
        pdf.drawString(470, y + 3, "LOTE")
        return y - 27

    # Primera página
    y = nueva_pagina(pdf, primera=True)
    y = dibujar_cabecera_tabla(pdf, y)

    detalle_wa = ""
    MARGEN_INF = 80   # espacio mínimo al pie antes de nueva página
    ALTO_FILA  = 27

    pdf.setFillColorRGB(0, 0, 0)

    for producto, cantidad in zip(productos_form, cantidades_form):

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

        # Fila con borde gris
        pdf.setStrokeColorRGB(0.7, 0.7, 0.7)
        pdf.rect(30, y - 5, ancho - 60, 22)
        pdf.setStrokeColorRGB(0, 0, 0)

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", 9)
        pdf.drawString(40,  y + 5, str(codigo))

        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont("Helvetica", 10)
        pdf.drawString(120, y + 5, str(nombre_producto))

        pdf.setFont("Helvetica-Bold", 11)
        pdf.drawString(385, y + 5, str(cantidad))

        # Lote vacío
        y -= ALTO_FILA
        detalle_wa += f"  • {nombre_producto} x{cantidad}\n"

    # Firma al final
    pdf.line(380, 80, 520, 80)
    pdf.setFont("Helvetica", 9)
    pdf.setFillColorRGB(0, 0, 0)
    pdf.drawString(430, 68, "Firma")

    pdf.save()

    # Guardar JSON
    pedido = {
        "vendedor": vendedor,
        "cliente":  cliente,
        "zona":     zona,
        "fecha_entrega": fecha_entrega_fmt,
        "detalle_productos": detalle_wa,
        "pdf":        nombre_pdf,
        "fecha_envio": fecha_envio
    }

    ruta_json = os.path.join("pedidos", nombre_pdf.replace(".pdf", ".json"))
    with open(ruta_json, "w") as f:
        json.dump(pedido, f, ensure_ascii=False, indent=2)

    return redirect(f"/ver_pdf/{nombre_pdf}")

# --------------------------------
# VER PDF
# --------------------------------

@app.route("/ver_pdf/<nombre>")
def ver_pdf(nombre):
    ruta_json = os.path.join("pedidos", nombre.replace(".pdf", ".json"))
    pedido = {}
    if os.path.exists(ruta_json):
        with open(ruta_json) as f:
            pedido = json.load(f)
    return render_template("ver_pdf.html", nombre=nombre, pedido=pedido)

# --------------------------------
# DESCARGAR PDF
# --------------------------------

@app.route("/pdf/<nombre>")
def pdf_archivo(nombre):
    return send_from_directory(directory="pedidos", path=nombre, as_attachment=True)

# --------------------------------
# VER PEDIDOS
# --------------------------------

@app.route("/pedidos")
def ver_pedidos():
    archivos = os.listdir("pedidos")
    return render_template("pedidos.html", archivos=archivos)

# --------------------------------
# AGREGAR PRODUCTOS
# --------------------------------

@app.route("/agregar_producto", methods=["GET", "POST"])
def agregar_producto():
    if request.method == "POST":
        codigo = request.form["codigo"]
        nombre = request.form["nombre"]
        with open("productos.json") as archivo:
            productos = json.load(archivo)
        productos.append({"codigo": codigo, "nombre": nombre})
        with open("productos.json", "w") as archivo:
            json.dump(productos, archivo)
        return redirect("/pedido")
    return render_template("agregar_producto.html")

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
