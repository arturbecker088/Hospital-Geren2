from database import obter_conexao


def processar_triagem(
    id_paciente, id_enfermeiro, classificacao, consciente
):
    conn = obter_conexao()
    if not conn:
        return False

    pesos = {
        "EMERGÊNCIA": 1,
        "MUITO URGENTE": 2,
        "URGENTE": 3,
        "POUCO URGENTE": 4,
        "NÃO URGENTE": 5
    }
    prioridade = pesos.get(classificacao, 5)

    try:
        cursor = conn.cursor()

        # Salva a triagem com a classificação já decidida pelo frontend
        cursor.execute(
            """
            INSERT INTO triagens (id_paciente, id_enfermeiro, consciente, pontuacao_sintomas, pontuacao_risco, pontuacao_total, classificacao)
            VALUES (%s, %s, %s, 0, 0, 0, %s) RETURNING id_triagem;
            """,
            (id_paciente, id_enfermeiro, consciente, classificacao),
        )
        id_triagem = cursor.fetchone()[0]

        # Adiciona na fila com prioridade
        cursor.execute(
            """
            INSERT INTO fila_atendimento (id_triagem, prioridade, status)
            VALUES (%s, %s, 'AGUARDANDO');
            """,
            (id_triagem, prioridade),
        )

        conn.commit()
        return {
            "status": "sucesso",
            "classificacao": classificacao,
            "prioridade": prioridade,
            "id_triagem": id_triagem,
        }

    except Exception as e:
        conn.rollback()
        print(f"Erro no processo de triagem: {e}")
        return None

    finally:
        cursor.close()
        conn.close()
