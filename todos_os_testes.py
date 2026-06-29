import sqlite3
import os

CAMINHO_BANCO = os.path.join(
    os.path.dirname(__file__),
    "banco.db"
)

conn = sqlite3.connect(CAMINHO_BANCO)
cursor = conn.cursor()

cursor.execute("""
UPDATE usuarios
SET plano_ativo = 1
WHERE usuario = 'admin'
""")

conn.commit()

cursor.execute("""
SELECT usuario, is_admin, plano_ativo
FROM usuarios
""")

for linha in cursor.fetchall():
    print(linha)

conn.close()