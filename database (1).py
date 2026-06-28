import os
import psycopg2
from dotenv import load_dotenv

load_dotenv()

def obter_conexao():
    url_banco = os.getenv("DATABASE_URL")
    if not url_banco:
        print("ERRO CRÍTICO: DATABASE_URL não encontrada!")
        return None
    try:
        return psycopg2.connect(url_banco)
    except Exception as e:
        print(f"Erro ao conectar ao Neon.tech: {e}")
        return None
