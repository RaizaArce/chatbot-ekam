"""Aplica los colores y proporciones del logo nuevo de EKAM PERU (azul marino + naranja)
al portal, a la ventana de chat de n8n y a las plantillas de Excel."""
import pathlib
import sys

sys.stdout.reconfigure(encoding="utf-8")
BASE = pathlib.Path(__file__).parent

CAMBIOS = {
    BASE / "portal" / "portal.html": [
        ("--azul: #1b1f4a; --azul-2: #2c3270; --azul-3: #3a418c; --dorado: #e5b800; --dorado-2: #fff6cc;",
         "--azul: #001858; --azul-2: #13307e; --azul-3: #24459f; --dorado: #f58a00; --dorado-2: #fff0dc;"),
        ("rgba(229,184,0,.18)", "rgba(245,138,0,.20)"),
        ("rgba(229,184,0,.2)", "rgba(245,138,0,.22)"),
        ("rgba(27,31,74,", "rgba(0,24,88,"),
        ("rgba(44,50,112,.12)", "rgba(19,48,126,.12)"),
        (".etiqueta.admin { background: var(--dorado-2); color: #7a6200; }", ".etiqueta.admin { background: var(--dorado-2); color: #9a5600; }"),
        ("border: 1px solid #f1dc85;", "border: 1px solid #f8c98a;"),
        # el logo nuevo es mas alto (proporcion 1.93 : 1)
        (".tarjeta .logo { width: 190px; height: 72px;", ".tarjeta .logo { width: 230px; height: 119px;"),
        (".lateral .logo { width: 150px; height: 56px; }", ".lateral .logo { width: 170px; height: 88px; }"),
        ("center / 86% no-repeat; border-radius: 10px;", "center / 92% no-repeat; border-radius: 10px;"),
        (".btn-dorado { background: var(--dorado); color: var(--azul); }", ".btn-dorado { background: var(--dorado); color: #fff; }"),
    ],
    BASE / "n8n" / "estilo_ekam.css": [
        ("--ekam-azul: #1b1f4a;", "--ekam-azul: #001858;"),
        ("--ekam-azul-claro: #2c3270;", "--ekam-azul-claro: #13307e;"),
        ("--ekam-dorado: #e5b800;", "--ekam-dorado: #f58a00;"),
        ("--chat--color--primary-shade-50: #cfa600;", "--chat--color--primary-shade-50: #e07e00;"),
        ("--chat--color--primary--shade-100: #b89400;", "--chat--color--primary--shade-100: #c96f00;"),
        ("rgba(27, 31, 74,", "rgba(0, 24, 88,"),
        ("padding-left: 190px !important;\n  min-height: 92px;", "padding-left: 190px !important;\n  min-height: 100px;"),
        ("width: 156px;\n  height: 60px;", "width: 156px;\n  height: 81px;"),
        ("center / 88% no-repeat;", "center / 92% no-repeat;"),
        (".chat-header::before { width: 92px; height: 38px; left: 12px; }", ".chat-header::before { width: 92px; height: 48px; left: 12px; }"),
    ],
    BASE / "faq" / "crear_borrador_faq.py": [('azul, dorado = "1B1F4A", "E5B800"', 'azul, dorado = "001858", "F58A00"'),
                                              ('fgColor="FFF6CC"', 'fgColor="FFF0DC"')],
    BASE / "faq" / "crear_plantilla_registro.py": [('AZUL, DORADO = "1B1F4A", "E5B800"', 'AZUL, DORADO = "001858", "F58A00"'),
                                                   ('color="9A7B00"', 'color="C46A00"'),
                                                   ('ws["K1"].font = Font(bold=True, color=AZUL)', 'ws["K1"].font = Font(bold=True, color="FFFFFF")')],
}

for archivo, cambios in CAMBIOS.items():
    texto = archivo.read_text(encoding="utf-8")
    faltan = [viejo for viejo, _ in cambios if viejo not in texto]
    for viejo, nuevo in cambios:
        texto = texto.replace(viejo, nuevo)
    archivo.write_text(texto, encoding="utf-8")
    print(f"{archivo.name}: {len(cambios) - len(faltan)} de {len(cambios)} cambios" + (f" | NO encontrados: {faltan}" if faltan else ""))
