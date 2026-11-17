"""Crea una plantilla nueva del registro de soporte: listas desplegables, fechas validadas
y una columna de 'pasos de la solucion' redactada para que sirva a otros clientes."""
import pathlib

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

AQUI = pathlib.Path(__file__).parent
AZUL, DORADO = "001858", "F58A00"
MODULOS = ["Facturación electrónica", "Ventas", "Compras / Cuentas por pagar", "Caja y Bancos", "Caja chica",
           "Contabilidad", "SIRE", "Inventarios / Almacén", "Entregas a rendir", "Guías de remisión",
           "Reportes", "Configuración / Accesos", "Instalación / Licencias", "Capacitación", "Otro"]
ESTADOS = ["Pendiente", "En proceso", "Derivado a Ingeniería", "Resuelto", "Cerrado"]
TIPOS = ["Duda de uso (cómo hacer algo)", "Error del sistema", "Error de SUNAT / externo", "Configuración",
         "Pedido de mejora / desarrollo", "Comercial (cotización, licencia)"]
FILAS = 1000

wb = Workbook()
ws = wb.active
ws.title = "Registro de Soporte"
columnas = [
    ("N.º", 6), ("Fecha", 12), ("Empresa / Cliente", 24), ("Contacto", 20), ("Teléfono", 13),
    ("Módulo", 22), ("Tipo de consulta", 26), ("Consulta del cliente (con sus palabras)", 45),
    ("Mensaje de error exacto (si hubo)", 32), ("Causa encontrada", 32),
    ("Pasos de la solución (para que otro cliente lo pueda hacer)", 55),
    ("¿Sirve para otros clientes? (SI/NO)", 14), ("¿Requiere manual nuevo? (SI/NO)", 14),
    ("Atendido por", 14), ("Estado", 14), ("Fecha de cierre", 13),
]
ws.append([c for c, _ in columnas])
for i, (_, ancho) in enumerate(columnas):
    ws.column_dimensions[chr(65 + i)].width = ancho
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor=AZUL)
    c.alignment = Alignment(wrap_text=True, vertical="center")
ws["K1"].fill = PatternFill("solid", fgColor=DORADO)
ws["K1"].font = Font(bold=True, color="FFFFFF")
ws.row_dimensions[1].height = 48
ws.freeze_panes = "C2"

listas = wb.create_sheet("Listas")
for col, (titulo, valores) in enumerate([("Módulos", MODULOS), ("Estados", ESTADOS), ("Tipos", TIPOS)], start=1):
    listas.cell(1, col, titulo).font = Font(bold=True)
    for fila, v in enumerate(valores, start=2):
        listas.cell(fila, col, v)
    listas.column_dimensions[chr(64 + col)].width = 30

def lista(rango_origen, celdas):
    dv = DataValidation(type="list", formula1=rango_origen, allow_blank=True, showErrorMessage=True,
                        errorTitle="Valor no válido", error="Elige una opción de la lista.")
    ws.add_data_validation(dv)
    dv.add(celdas)

lista(f"=Listas!$A$2:$A${len(MODULOS) + 1}", f"F2:F{FILAS}")
lista(f"=Listas!$C$2:$C${len(TIPOS) + 1}", f"G2:G{FILAS}")
lista(f"=Listas!$B$2:$B${len(ESTADOS) + 1}", f"O2:O{FILAS}")
lista('"SI,NO"', f"L2:M{FILAS}")
fechas = DataValidation(type="date", operator="between", formula1="DATE(2024,1,1)", formula2="DATE(2035,12,31)",
                        showErrorMessage=True, errorTitle="Fecha no válida", error="Escribe una fecha válida (dd/mm/aaaa).")
ws.add_data_validation(fechas)
fechas.add(f"B2:B{FILAS}")
fechas.add(f"P2:P{FILAS}")
for fila in ws.iter_rows(min_row=2, max_row=FILAS):
    fila[1].number_format = fila[15].number_format = "DD/MM/YYYY"
    for c in fila:
        c.alignment = Alignment(wrap_text=True, vertical="top")

guia = wb.create_sheet("Cómo llenarlo", 0)
texto = [
    "REGISTRO DE SOPORTE – EKAM PERÚ",
    "",
    "Este registro sirve para dos cosas: llevar el control de las atenciones y, sobre todo, que lo que resolvemos hoy",
    "le sirva al próximo cliente (y al Asistente NAVASOFT).",
    "",
    "La columna más importante es la DORADA: 'Pasos de la solución'.",
    "  ✗ Mal:  \"Se le atendió\", \"Se verificó\", \"Se coordinó por AnyDesk\"",
    "  ✓ Bien: \"1. Ir a Contabilidad → Asientos. 2. Doble clic en el ícono rojo de la alerta para ver la cuenta con error.",
    "           3. Reemplazar la cuenta por la correcta del plan contable y grabar.\"",
    "",
    "Otras recomendaciones:",
    "  • Copia el mensaje de error EXACTO (o pega una captura en la carpeta de evidencias).",
    "  • Usa las listas desplegables de Módulo, Tipo y Estado: así se pueden sacar estadísticas.",
    "  • Marca '¿Requiere manual nuevo?' = SI cuando el tema no esté en ningún manual.",
    "",
    "SEGURIDAD: no guardes contraseñas, IDs de AnyDesk ni claves de clientes en este archivo.",
    "Usa un gestor de contraseñas.",
]
for linea in texto:
    guia.append([linea])
guia.column_dimensions["A"].width = 130
guia["A1"].font = Font(bold=True, size=14, color=AZUL)
guia["A6"].font = Font(bold=True, color="C46A00")
guia["A16"].font = Font(bold=True, color="C00000")

destino = AQUI / "Plantilla_Registro_Soporte_EKAM.xlsx"
wb.save(destino)
print("Creado:", destino)
