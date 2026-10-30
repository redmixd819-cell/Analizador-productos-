import os
import requests
from flask import Flask, request, jsonify, render_template
from pytrends.request import TrendReq

app = Flask(__name__)

HEADERS = {"User-Agent": "Mozilla/5.0"}


def datos_trends(producto):
    """Devuelve (interes_promedio_0_100, tendencia_pct) para Argentina."""
    try:
        pt = TrendReq(hl="es-AR", tz=180)
        pt.build_payload([producto], geo="AR", timeframe="today 12-m")
        df = pt.interest_over_time()
        if df.empty:
            return 0, 0
        serie = df[producto].tolist()
        promedio = sum(serie) / len(serie)
        mitad = len(serie) // 2
        antes = sum(serie[:mitad]) / max(mitad, 1)
        despues = sum(serie[mitad:]) / max(len(serie) - mitad, 1)
        tendencia = ((despues - antes) / antes * 100) if antes else 0
        return promedio, tendencia
    except Exception:
        return None, None


def datos_mercadolibre(producto):
    """Devuelve (total_publicaciones, ventas_promedio, precio_promedio, top)."""
    try:
        url = "https://api.mercadolibre.com/sites/MLA/search"
        r = requests.get(url, params={"q": producto, "limit": 50},
                         headers=HEADERS, timeout=15)
        data = r.json()
        total = data.get("paging", {}).get("total", 0)
        items = data.get("results", [])
        if not items:
            return total, 0, 0, []
        ventas = [i.get("sold_quantity", 0) for i in items]
        precios = [i.get("price", 0) for i in items]
        top = sorted(items, key=lambda i: i.get("sold_quantity", 0),
                     reverse=True)[:5]
        top = [{"titulo": i["title"], "precio": i["price"],
                "vendidos": i.get("sold_quantity", 0),
                "link": i["permalink"]} for i in top]
        return total, sum(ventas) / len(ventas), sum(precios) / len(precios), top
    except Exception:
        return None, None, None, []


def escala(valor, minimo, maximo):
    if valor is None:
        return 0
    valor = max(minimo, min(maximo, valor))
    return (valor - minimo) / (maximo - minimo) * 100


@app.route("/")
def inicio():
    return render_template("index.html")


@app.route("/analizar")
def analizar():
    producto = request.args.get("producto", "").strip()
    if not producto:
        return jsonify({"error": "Escribí un producto"}), 400

    interes, tendencia = datos_trends(producto)
    total, ventas_prom, precio_prom, top = datos_mercadolibre(producto)

    # Puntajes parciales de 0 a 100
    p_interes = escala(interes, 0, 60)
    if tendencia is not None:
        p_interes = min(100, max(0, p_interes + escala(tendencia, -50, 50) * 0.3 - 15))
    p_demanda = escala(ventas_prom, 0, 100)
    # Más publicaciones = más competencia = menor puntaje
    p_competencia = 100 - escala(total, 100, 20000)

    puntaje = round(p_interes * 0.4 + p_demanda * 0.4 + p_competencia * 0.2)

    if puntaje >= 70:
        veredicto = "Rotación alta"
    elif puntaje >= 40:
        veredicto = "Rotación media"
    else:
        veredicto = "Rotación baja"

    return jsonify({
        "producto": producto,
        "puntaje": puntaje,
        "veredicto": veredicto,
        "interes_google": None if interes is None else round(interes),
        "tendencia_pct": None if tendencia is None else round(tendencia),
        "publicaciones_ml": total,
        "ventas_promedio_ml": None if ventas_prom is None else round(ventas_prom),
        "precio_promedio_ars": None if precio_prom is None else round(precio_prom),
        "top_ml": top,
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
