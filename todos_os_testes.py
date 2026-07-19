import sqlite3
import os

CAMINHO_BANCO = os.path.join(
    os.path.dirname(__file__),
    "banco.db"
)

conn = sqlite3.connect(CAMINHO_BANCO)
cursor = conn.cursor()

cursor.execute("PRAGMA table_info(clientes)")

for coluna in cursor.fetchall():
    print(coluna)

conn.close()
