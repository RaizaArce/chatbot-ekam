"""Crea la cuenta de administracion inicial y dos cuentas de prueba, con contrasenas aleatorias.
Las contrasenas se guardan en portal/credenciales_iniciales.txt (solo en esta PC).
La cuenta admin.ekam debe cambiar su contrasena en el primer ingreso."""
import pathlib
import secrets
import string
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
from leer_manuales import conectar  # noqa: E402

sys.stdout.reconfigure(encoding="utf-8")
AQUI = pathlib.Path(__file__).parent
ALFABETO = "".join(c for c in string.ascii_letters + string.digits if c not in "0OolI1")


def clave():
    return "".join(secrets.choice(ALFABETO) for _ in range(12))


CUENTAS = [  # usuario, nombre, empresa, rol, debe_cambiar
    ("admin.ekam", "Administración EKAM", "EKAM PERÚ", "admin", True),
    ("prueba.admin", "Prueba Administrador", "EKAM PERÚ", "admin", False),
    ("cliente.prueba", "Cliente de Prueba", "Empresa Demo SAC", "cliente", False),
]

con = conectar()
lineas = ["CUENTAS INICIALES DEL PORTAL NAVASOFT (guardar en un lugar seguro y borrar este archivo después)", ""]
for usuario, nombre, empresa, rol, cambiar in CUENTAS:
    if con.execute("SELECT 1 FROM usuarios WHERE usuario = %s", (usuario,)).fetchone():
        print(f"Ya existe: {usuario} (no se cambia)")
        continue
    c = clave()
    con.execute(
        "INSERT INTO usuarios (usuario, nombre, empresa, clave_hash, rol, debe_cambiar) "
        "VALUES (%s, %s, %s, crypt(%s, gen_salt('bf', 10)), %s, %s)",
        (usuario, nombre, empresa, c, rol, cambiar),
    )
    lineas.append(f"{usuario:<16} rol={rol:<8} contraseña={c}" + ("   (pedirá cambiarla al ingresar)" if cambiar else ""))
    print(f"Creada: {usuario} ({rol})")

archivo = AQUI / "credenciales_iniciales.txt"
if len(lineas) > 2:
    with archivo.open("a", encoding="utf-8") as f:
        f.write("\n".join(lineas) + "\n\n")
    print("Contraseñas guardadas en:", archivo)
