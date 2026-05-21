from flask import (
    Flask,
    render_template,
    request,
    redirect,
    session,
    send_from_directory
)

from reportlab.pdfgen import canvas
from datetime import datetime
import json
import os

app = Flask(__name__)

app.secret_key = "DFsystem"

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

    usuarios = {"walter": "1234"}

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

    dias = {
        "Monday": "🌸 Hoy es un gran día para crecer.",
        "Tuesday": "✨ Todo esfuerzo trae resultados.",
        "Wednesday": "💎 Estás más cerca de tus metas.",
        "Thursday": "🚀 Con paciencia todo mejora.",
        "Friday": "🎀 Terminando la semana con fuerza.",
        "Saturday": "🌷 Descansar también es avanzar.",
        "Sunday": "☀️ Nuevo día, nuevas oportunidades."
    }

    dia_actual = datetime.now().strftime("%A")
    frase = dias.get(dia_actual, "✨ Bienvenida a DF SYSTEM")
    fecha_actual = datetime.now().strftime("%d/%m/%Y - %H:%M")

    return render_template(
        "pedido.html",
        productos=productos,
        usuario=session["usuario"],
        fecha=fecha_actual,
        frase=frase
    )

# --------------------------------
# GENERAR PDF
# --------------------------------

@app.route("/generar", methods=["POST"])
def generar():

    cliente = request.form["cliente"]
    razon = request.form["razon"]
    zona = request.form["zona"]
    fecha_entrega = request.form["fecha_entrega"]
    nota = request.form["nota"]

    productos = request.form.getlist("producto[]")
    cantidades = request.form.getlist("cantidad[]")

    fecha_envio = datetime.now().strftime("%d-%m-%Y %H:%M")

    if not os.path.exists("pedidos"):
        os.makedirs("pedidos")

    nombre_pdf = f"Pedido_{datetime.now().strftime('%d-%m-%Y_%H-%M')}.pdf"
    ruta = os.path.join("pedidos", nombre_pdf)

    # CREAR PDF
    pdf = canvas.Canvas(ruta)

    pdf.setLineWidth(1)
    pdf.rect(30, 40, 535, 780)

    pdf.setFont("Helvetica-Bold", 14)
    pdf.drawString(45, 800, "★ DF SYSTEM")
    pdf.setFont("Helvetica-Bold", 18)
    pdf.drawString(190, 800, "NOTA DE PEDIDO")

    pdf.setFont("Helvetica", 11)
    pdf.drawString(50, 750, f"Vendedor: {session['usuario']}")
    pdf.drawString(50, 730, f"Cliente: {cliente}")
    pdf.drawString(50, 710, f"Razón Social: {razon}")
    pdf.drawString(50, 690, f"Zona: {zona}")
    pdf.drawString(320, 750, f"Fecha Entrega: {fecha_entrega}")
    pdf.drawString(320, 730, f"Fecha Envío: {fecha_envio}")
    pdf.drawString(50, 660, f"Nota: {nota}")

    pdf.setFont("Helvetica-Bold", 11)
    pdf.rect(40, 600, 500, 25)
    pdf.drawString(55, 608, "Código")
    pdf.drawString(140, 608, "Producto")
    pdf.drawString(340, 608, "Cantidad")
    pdf.drawString(450, 608, "Lote")

    y = 575
    pdf.setFont("Helvetica", 10)

    detalle_wa = ""

    for producto, cantidad in zip(productos, cantidades):

        if " - " in producto:
            partes = producto.split(" - ")
            codigo = partes[0]
            nombre_producto = partes[1]
        else:
            codigo = "-"
            nombre_producto = producto

        pdf.rect(40, y - 5, 500, 25)
        pdf.drawString(55, y + 5, str(codigo))
        pdf.drawString(140, y + 5, str(nombre_producto))
        pdf.drawString(350, y + 5, str(cantidad))
        pdf.drawString(455, y + 5, "-")
        y -= 30

        detalle_wa += f"  • {nombre_producto} x{cantidad}\n"

    pdf.line(380, 120, 520, 120)
    pdf.drawString(420, 105, "Firma")
    pdf.save()

    # GUARDAR DATOS DEL PEDIDO EN JSON
    pedido = {
        "vendedor": session["usuario"],
        "cliente": cliente,
        "zona": zona,
        "fecha_entrega": fecha_entrega,
        "detalle_productos": detalle_wa,
        "pdf": nombre_pdf,
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

    return render_template(
        "ver_pdf.html",
        nombre=nombre,
        pedido=pedido
    )

# --------------------------------
# DESCARGAR PDF
# --------------------------------

@app.route("/pdf/<nombre>")
def pdf_archivo(nombre):

    return send_from_directory(
        directory="pedidos",
        path=nombre,
        as_attachment=True
    )

# --------------------------------
# VER PEDIDOS
# --------------------------------

@app.route("/pedidos")
def ver_pedidos():

    archivos = os.listdir("pedidos")

    return render_template(
        "pedidos.html",
        archivos=archivos
    )

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