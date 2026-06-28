from database import obter_conexao
import traceback


def processar_triagem(
    id_paciente, id_enfermeiro, classificacao, consciente
):
    conn = obter_conexao()
    if not conn:
        print("ERRO: sem conexão com banco")
        return False

    pesos = {
        "EMERGÊNCIA": 1,
        "MUITO URGENTE": 2,
        "URGENTE": 3,
        "POUCO URGENTE": 4,
        "NÃO URGENTE": 5
    }
    prioridade = pesos.get(classificacao, 5)
    print(f"Iniciando triagem: paciente={id_paciente}, classificacao={classificacao}, prioridade={prioridade}")

    try:
        cursor = conn.cursor()

        print("Inserindo na tabela triagens...")
        cursor.execute(
            """
            INSERT INTO triagens (id_paciente, id_enfermeiro, consciente, pontuacao_sintomas, pontuacao_risco, pontuacao_total, classificacao)
            VALUES (%s, %s, %s, 0, 0, 0, %s) RETURNING id_triagem;
            """,
            (id_paciente, id_enfermeiro, consciente, classificacao),
        )
        id_triagem = cursor.fetchone()[0]
        print(f"Triagem inserida com id={id_triagem}")

        print("Inserindo na fila_atendimento...")
        cursor.execute(
            """
            INSERT INTO fila_atendimento (id_triagem, prioridade, status)
            VALUES (%s, %s, 'AGUARDANDO');
            """,
            (id_triagem, prioridade),
        )
        print("Fila inserida com sucesso!")

        conn.commit()
        return {
            "status": "sucesso",
            "classificacao": classificacao,
            "prioridade": prioridade,
            "id_triagem": id_triagem,
        }

    except Exception as e:
        conn.rollback()
        print(f"ERRO TRIAGEM: {e}")
        traceback.print_exc()
        return None

    finally:
        cursor.close()
        conn.close()
