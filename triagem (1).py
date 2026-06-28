from database import obter_conexao


def processar_triagem(
    id_paciente, id_enfermeiro, lista_id_sintomas, id_comorbidades, consciente
):
    conn = obter_conexao()
    if not conn:
        return False

    try:
        cursor = conn.cursor()

        if not consciente:
            pontuacao_total = 100
            classificacao = "EMERGÊNCIA"
            prioridade = 1

        else:
            # Soma pontos dos sintomas
            pontos_sintomas = 0
            if lista_id_sintomas:
                format_sintomas = ",".join("%s" for _ in lista_id_sintomas)
                cursor.execute(
                    f"SELECT COALESCE(SUM(pontuacao), 0) FROM sintomas WHERE id_sintomas IN ({format_sintomas})",
                    tuple(lista_id_sintomas),
                )
                pontos_sintomas = cursor.fetchone()[0] or 0

            # Soma pontos das comorbidades
            pontos_comorbidades = 0
            if id_comorbidades:
                format_comorbidades = ",".join("%s" for _ in id_comorbidades)
                cursor.execute(
                    f"SELECT COALESCE(SUM(pontuacao_extra), 0) FROM comorbidades WHERE id_comorbidade IN ({format_comorbidades})",
                    tuple(id_comorbidades),
                )
                pontos_comorbidades = cursor.fetchone()[0] or 0

            pontuacao_total = pontos_sintomas + pontos_comorbidades

            # Busca classificação pela pontuação total
            cursor.execute(
                """
                SELECT classificacao, prioridade
                FROM regras_classificacao
                WHERE %s BETWEEN min_pontos AND max_pontos
                LIMIT 1
                """,
                (pontuacao_total,),
            )
            regra = cursor.fetchone()
            classificacao = regra[0] if regra else "NÃO URGENTE"
            prioridade = regra[1] if regra else 5

        # Salva a triagem
        cursor.execute(
            """
            INSERT INTO triagens (id_paciente, id_enfermeiro, consciente, pontuacao_sintomas, pontuacao_risco, pontuacao_total, classificacao, prioridade)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id_triagem;
            """,
            (
                id_paciente,
                id_enfermeiro,
                consciente,
                pontos_sintomas if consciente else 0,
                pontos_comorbidades if consciente else 0,
                pontuacao_total,
                classificacao,
                prioridade,
            ),
        )
        id_triagem = cursor.fetchone()[0]

        # Vincula sintomas
        for id_sintoma in lista_id_sintomas:
            cursor.execute(
                "INSERT INTO triagem_sintomas (id_triagem, id_sintoma) VALUES (%s, %s);",
                (id_triagem, id_sintoma),
            )

        # Adiciona na fila
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
