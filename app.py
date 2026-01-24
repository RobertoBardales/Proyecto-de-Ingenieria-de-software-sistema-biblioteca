from app import create_app

app = create_app()

# Register filter BEFORE app.run()
@app.template_filter('numero_a_letras')
def numero_a_letras(numero):
    """Convert number to Spanish words (for invoice totals)"""
    unidades = ['', 'UN', 'DOS', 'TRES', 'CUATRO', 'CINCO', 'SEIS', 'SIETE', 'OCHO', 'NUEVE']
    decenas = ['', 'DIEZ', 'VEINTE', 'TREINTA', 'CUARENTA', 'CINCUENTA', 'SESENTA', 'SETENTA', 'OCHENTA', 'NOVENTA']
    especiales = ['DIEZ', 'ONCE', 'DOCE', 'TRECE', 'CATORCE', 'QUINCE', 'DIECISÉIS', 'DIECISIETE', 'DIECIOCHO', 'DIECINUEVE']
    centenas = ['', 'CIENTO', 'DOSCIENTOS', 'TRESCIENTOS', 'CUATROCIENTOS', 'QUINIENTOS', 'SEISCIENTOS', 'SETECIENTOS', 'OCHOCIENTOS', 'NOVECIENTOS']
    
    try:
        numero = float(numero)
        entero = int(numero)
        decimal = int(round((numero - entero) * 100))
        
        if entero == 0:
            return f"CERO CON {decimal:02d}/100"
        
        if entero > 999999:
            return f"{entero:,.2f}"
        
        def convertir_grupo(n):
            if n == 0:
                return ''
            elif n < 10:
                return unidades[n]
            elif n < 20:
                return especiales[n - 10]
            elif n < 100:
                d, u = divmod(n, 10)
                if u == 0:
                    return decenas[d]
                else:
                    return f"{decenas[d]} Y {unidades[u]}"
            else:
                c, resto = divmod(n, 100)
                if c == 1 and resto == 0:
                    return 'CIEN'
                elif resto == 0:
                    return centenas[c]
                else:
                    return f"{centenas[c]} {convertir_grupo(resto)}"
        
        miles, resto = divmod(entero, 1000)
        
        resultado = ''
        if miles > 0:
            if miles == 1:
                resultado = 'MIL'
            else:
                resultado = f"{convertir_grupo(miles)} MIL"
        
        if resto > 0:
            if resultado:
                resultado += f" {convertir_grupo(resto)}"
            else:
                resultado = convertir_grupo(resto)
        
        return f"{resultado} CON {decimal:02d}/100"
    
    except:
        return "ERROR EN CONVERSIÓN"

if __name__ == '__main__':
    print("Iniciando Flask...")
    app.run(debug=True, host='127.0.0.1', port=5001)