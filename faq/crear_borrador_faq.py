"""Crea el borrador de Preguntas Frecuentes a partir de los casos reutilizables del registro de soporte.
Cada respuesta esta redactada SOLO con lo que dice el caso original (sin agregar pasos).
Ninguna entra al chatbot hasta que una ingeniera marque 'Validado = SI' (ver cargar_faq.py)."""
import pathlib

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

AQUI = pathlib.Path(__file__).parent

# (caso, modulo, pregunta del cliente, respuesta propuesta, publico, que falta confirmar)
FAQ = [
    (68, "Contabilidad",
     "Al modificar o grabar el asiento de apertura generado automáticamente aparece el mensaje de error \"FOREIGN KEY CUENTA\". ¿Qué hago?",
     "1. Haz doble clic en el ícono rojo del mensaje de alerta: el sistema te indica qué cuenta está generando el error.\n2. En el detalle del asiento, reemplaza esa cuenta por la cuenta correcta del plan contable.\n3. Vuelve a grabar el asiento.",
     "Cliente", "Confirmar que el doble clic en el ícono rojo funciona en todas las versiones."),
    (69, "Contabilidad / SIRE",
     "Al ingresar a SIRE desde NAVASOFT sale el mensaje \"Generar Registro – FALLA EN LA COMUNICACIÓN\". ¿Qué puedo revisar?",
     "Verifica que las credenciales configuradas para SIRE tengan acceso: con esas mismas credenciales ingresa directamente a SUNAT con tu Clave SOL y confirma que puedes entrar a la consulta de SIRE. Si desde SUNAT tampoco tienes acceso, el problema está en las credenciales y no en NAVASOFT.",
     "Cliente", "Indicar dónde se configuran las credenciales SIRE dentro de NAVASOFT."),
    (65, "Contabilidad / SIRE",
     "Un comprobante con cargos aparece como 'no gravado' y genera diferencia con la propuesta del SIRE. ¿Cómo hago que aparezca en la columna correcta?",
     "Para que el importe se consigne en la columna \"Otros\" del SIRE, en el asiento contable del comprobante ese cargo debe ir en una cuenta 40x registrada como inafecta.",
     "Cliente", "Confirmar qué subcuenta 40x usar y si aplica a todos los tipos de cargo."),
    (3, "Tesorería / Caja",
     "Debo devolver dinero a un cliente por una nota de crédito y el dinero sale de caja. ¿Cuál es el procedimiento?",
     "1. Genera un Recibo de egreso en caja.\n2. Como motivo de pago elige \"pago por cuenta del cliente\".\n3. Selecciona al cliente y luego la nota de crédito que estás devolviendo.",
     "Cliente", "Confirmar el nombre exacto del motivo de pago y la ruta del menú."),
    (5, "Ventas / Facturación",
     "Al emitir una factura al contado aparece el mensaje \"importe depositado no es válido\" y no me deja continuar.",
     "En una venta al contado el cliente paga el total, por lo que el importe cobrado debe ser igual al importe de la factura. Si el cliente solo paga una parte, la factura no debe registrarse al contado.",
     "Cliente", "Indicar qué condición de pago usar cuando el pago es parcial (crédito, cuotas, etc.)."),
    (10, "Facturación electrónica",
     "Quiero cambiar la serie de un documento electrónico ya emitido y el sistema dice que no estoy autorizado.",
     "Los documentos electrónicos ya emitidos no permiten modificaciones, solo anulación. Si un dato es incorrecto, debes anular el documento (o emitir la nota de crédito que corresponda) y emitir uno nuevo.",
     "Cliente", "Confirmar si corresponde anulación o nota de crédito según el caso."),
    (72, "Ventas / Facturación electrónica",
     "Necesito emitir notas de crédito a boletas que anulé en NAVASOFT, pero en SUNAT figuran como emitidas.",
     "Si las boletas siguen vigentes en SUNAT, primero deben reactivarse en NAVASOFT y recién después se registran las notas de crédito. Comunícate con soporte de EKAM PERÚ para reactivar las boletas.",
     "Cliente", "Confirmar si el cliente puede reactivar las boletas por sí mismo y cómo."),
    (53, "Contabilidad / Reportes",
     "En el reporte por ID de referencia el pago no se relaciona con su provisión (solo aparecen los pagos).",
     "La provisión (registrada en el auxiliar o en el asiento de apertura) y el pago en Bancos deben tener el mismo ID de referencia y el mismo documento de referencia. Revisa que ambos coincidan.",
     "Cliente", "Indicar en qué ventana se corrige el ID de referencia."),
    (67, "Contabilidad / Reportes",
     "En el reporte de ID de referencia de la cuenta 1212 un comprobante aparece pendiente, pero ya fue cancelado con nota de crédito.",
     "Revisa el asiento de apertura: el comprobante debe estar registrado como pendiente por cobrar en la cuenta 1212. Si no está registrado ahí, el reporte no puede cruzarlo con la nota de crédito.",
     "Cliente", "Confirmar el procedimiento para corregir el asiento de apertura."),
    (43, "Facturación",
     "Necesito registrar una nota de crédito que hace referencia a una factura diferida y no la encuentro.",
     "Revisa si el cliente está registrado en \"Clientes Varios\" o si figura como \"Inactivo\".",
     "Cliente", "Completar: qué hacer después de ubicar al cliente."),
    (22, "Facturación",
     "Al emitir una nota de débito, ¿cómo hago que el sistema solicite el documento de referencia?",
     "Debes configurar la glosa del motivo de la nota de débito para que solicite referencia.",
     "Cliente", "Indicar la ruta donde se configura la glosa del motivo."),
    (17, "Configuración / Guías",
     "En la guía de remisión el nombre del transportista sale distinto al que se seleccionó.",
     "Revisar en la tabla de transportistas que el campo ESTADO tenga por defecto el valor 'activo' y actualizar todos los registros a estado activo.",
     "Solo soporte interno", "Requiere acceso a la base de datos: no debe darse al cliente."),
]

wb = Workbook()
ws = wb.active
ws.title = "Borrador FAQ"
cab = ["N.º", "Caso original (N.º del registro)", "Módulo", "Pregunta del cliente", "Respuesta propuesta",
       "Público", "Falta confirmar", "Validado (SI/NO)", "Respuesta corregida por la ingeniera", "Validado por", "Fecha"]
ws.append(cab)
for i, (caso, mod, preg, resp, pub, falta) in enumerate(FAQ, start=1):
    ws.append([i, caso, mod, preg, resp, pub, falta, "NO", "", "", ""])

azul, dorado = "001858", "F58A00"
for c in ws[1]:
    c.font = Font(bold=True, color="FFFFFF")
    c.fill = PatternFill("solid", fgColor=azul)
    c.alignment = Alignment(wrap_text=True, vertical="center")
for col, ancho in zip("ABCDEFGHIJK", [5, 12, 18, 45, 60, 14, 35, 12, 45, 16, 12]):
    ws.column_dimensions[col].width = ancho
for fila in ws.iter_rows(min_row=2):
    for c in fila:
        c.alignment = Alignment(wrap_text=True, vertical="top")
    fila[7].fill = PatternFill("solid", fgColor="FFF0DC")
ws.freeze_panes = "D2"
dv = DataValidation(type="list", formula1='"SI,NO"', allow_blank=False)
ws.add_data_validation(dv)
dv.add(f"H2:H{len(FAQ) + 1}")

info = wb.create_sheet("Cómo validar")
for linea in [
    "BORRADOR DE PREGUNTAS FRECUENTES – Asistente NAVASOFT",
    "",
    "Estas respuestas se redactaron SOLO con lo que dice cada caso del registro de soporte. No se agregaron pasos.",
    "Ninguna se muestra a clientes hasta que una ingeniera la valide.",
    "",
    "Para cada fila:",
    "1. Lee la pregunta y la respuesta propuesta.",
    "2. Si hace falta, escribe la versión correcta en 'Respuesta corregida por la ingeniera' (completa lo indicado en 'Falta confirmar').",
    "3. Cambia 'Validado' a SI, y completa tu nombre y la fecha.",
    "4. Las filas con Público = 'Solo soporte interno' no se cargan al chatbot de clientes.",
    "",
    "Se puede agregar filas nuevas con otras preguntas frecuentes siguiendo el mismo formato.",
]:
    info.append([linea])
info.column_dimensions["A"].width = 120
info["A1"].font = Font(bold=True, size=14, color=azul)

destino = AQUI / "Borrador_Preguntas_Frecuentes_NAVASOFT.xlsx"
wb.save(destino)
print(f"Creado: {destino} ({len(FAQ)} preguntas)")
