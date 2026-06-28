from flask import Flask, jsonify, request
from flask_cors import CORS
from database import obter_conexao
from triagem import processar_triagem
import os

app = Flask(__name__)
CORS(app)  # Permite o frontend do GitHub Pages falar com essa API


# ─── ROTA DE TESTE ───────────────────────────────────────
@app.route('/', methods=['GET'])
def index():
    return jsonify({"status": "Hospisys API rodando!"})


# ─── CRIAR OU BUSCAR PACIENTE ────────────────────────────
@app.route('/pacientes', methods=['POST'])
def criar_paciente():
    dados = request.get_json()
    nome = dados.get('nome', '').strip()
    cpf = dados.get('cpf', '').replace('.', '').replace('-', '').strip()
    data_nascimento = dados.get('data_nascimento', '').strip()

    # Validações básicas
    if not nome:
        return jsonify({"erro": "Nome é obrigatório"}), 400
    if len(cpf) != 11 or not cpf.isdigit():
        return jsonify({"erro": f"CPF inválido: '{cpf}'. Deve ter exatamente 11 dígitos numéricos."}), 400

    # Valida formato e valor da data (esperado: YYYY-MM-DD)
    from datetime import date
    try:
        from datetime import datetime
        data_obj = datetime.strptime(data_nascimento, '%Y-%m-%d').date()
        if data_obj > date.today() or data_obj.year < 1900:
            return jsonify({"erro": f"Data de nascimento inválida: '{data_nascimento}'"}), 400
    except (ValueError, TypeError):
        return jsonify({"erro": f"Formato de data inválido: '{data_nascimento}'. Esperado YYYY-MM-DD."}), 400

    conn = obter_conexao()
    if not conn:
        return jsonify({"erro": "Falha na conexão com o banco"}), 500

    try:
        cursor = conn.cursor()
        # Busca por CPF normalizado (só números)
        cursor.execute("SELECT id_paciente FROM pacientes WHERE REPLACE(REPLACE(cpf, '.', ''), '-', '') = %s", (cpf,))
        existente = cursor.fetchone()
        if existente:
            return jsonify({"id_paciente": existente[0]})
        # Cria novo
        cursor.execute(
            "INSERT INTO pacientes (nome, cpf, data_nascimento) VALUES (%s, %s, %s) RETURNING id_paciente",
            (nome, cpf, data_nascimento)
        )
        id_paciente = cursor.fetchone()[0]
        conn.commit()
        return jsonify({"id_paciente": id_paciente}), 201
    except Exception as e:
        conn.rollback()
        print(f"Erro ao criar paciente: {e}")
        return jsonify({"erro": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ─── SALVAR TRIAGEM ──────────────────────────────────────
@app.route('/triagens', methods=['POST'])
def nova_triagem():
    dados = request.get_json()
    print(f"Dados recebidos: {dados}")
    try:
        resultado = processar_triagem(
            id_paciente=dados['id_paciente'],
            id_enfermeiro=dados.get('id_enfermeiro', 1),
            classificacao=dados.get('classificacao', 'NÃO URGENTE'),
            consciente=dados.get('consciente', True),
            sintomas_texto=dados.get('sintomas_texto', ''),
            comorbidades_texto=dados.get('comorbidades_texto', ''),
            veredito_texto=dados.get('veredito_texto', ''),
            protocolo_texto=dados.get('protocolo_texto', '')
        )
        print(f"Resultado triagem: {resultado}")
        if resultado:
            return jsonify(resultado), 201
        return jsonify({"erro": "Falha ao salvar triagem"}), 500
    except Exception as e:
        print(f"ERRO DETALHADO: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"erro": str(e)}), 500


# ─── BUSCAR FILA ─────────────────────────────────────────
@app.route('/fila', methods=['GET'])
def buscar_fila():
    conn = obter_conexao()
    if not conn:
        return jsonify({"erro": "Falha na conexão"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT f.id_triagem, p.nome, f.prioridade, f.status,
                   t.classificacao, f.hora_entrada,
                   t.sintomas_texto, t.comorbidades_texto, t.veredito_texto, t.protocolo_texto
            FROM fila_atendimento f
            JOIN triagens t ON f.id_triagem = t.id_triagem
            JOIN pacientes p ON t.id_paciente = p.id_paciente
            WHERE f.status = 'AGUARDANDO'
            ORDER BY f.prioridade ASC, f.hora_entrada ASC
        """)
        rows = cursor.fetchall()
        fila = [
            {
                "id_triagem": r[0],
                "nome_paciente": r[1],
                "prioridade": r[2],
                "status": r[3],
                "classificacao": r[4],
                "data_entrada": str(r[5]),
                "sintomas_texto": r[6] or "",
                "comorbidades_texto": r[7] or "",
                "veredito_texto": r[8] or "",
                "protocolo_texto": r[9] or ""
            } for r in rows
        ]
        return jsonify(fila)

    except Exception as e:
        print(f"Erro ao buscar fila: {e}")
        return jsonify({"erro": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ─── CHAMAR PACIENTE ─────────────────────────────────────
@app.route('/fila/<int:id_triagem>/chamar', methods=['PATCH'])
def chamar_paciente(id_triagem):
    conn = obter_conexao()
    if not conn:
        return jsonify({"erro": "Falha na conexão"}), 500

    try:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE fila_atendimento SET status = 'CHAMADO' WHERE id_triagem = %s",
            (id_triagem,)
        )
        conn.commit()
        return jsonify({"status": "chamado"})
    except Exception as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


# ─── EMERGÊNCIA DIRETA ────────────────────────────────────
@app.route('/emergencia', methods=['POST'])
def emergencia_direta():
    dados = request.get_json()
    nome = dados.get('nome', 'PACIENTE NÃO IDENTIFICADO')
    obs = dados.get('observacao', 'Acionamento direto de emergência.')

    conn = obter_conexao()
    if not conn:
        return jsonify({"erro": "Falha na conexão"}), 500

    try:
        cursor = conn.cursor()

        # Cria paciente temporário com CPF único baseado no timestamp
        import time
        cpf_temp = str(int(time.time()))[-11:].zfill(11)
        cursor.execute(
            "INSERT INTO pacientes (nome, cpf, data_nascimento) VALUES (%s, %s, %s) RETURNING id_paciente",
            (nome, cpf_temp, '1900-01-01')
        )
        id_paciente = cursor.fetchone()[0]

        # Cria triagem de emergência
        cursor.execute(
            """
            INSERT INTO triagens (id_paciente, id_enfermeiro, consciente, pontuacao_sintomas, pontuacao_risco, pontuacao_total, classificacao)
            VALUES (%s, 1, false, 0, 0, 100, 'VERMELHO') RETURNING id_triagem
            """,
            (id_paciente,)
        )
        id_triagem = cursor.fetchone()[0]

        # Adiciona na frente da fila
        cursor.execute(
            "INSERT INTO fila_atendimento (id_triagem, prioridade, status) VALUES (%s, 1, 'AGUARDANDO')",
            (id_triagem,)
        )

        conn.commit()
        return jsonify({"status": "sucesso", "id_triagem": id_triagem}), 201

    except Exception as e:
        conn.rollback()
        return jsonify({"erro": str(e)}), 500
    finally:
        cursor.close()
        conn.close()


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
