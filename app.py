
from flask import Flask, render_template, request, redirect, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
from dotenv import load_dotenv
from pathlib import Path
import psycopg
import os

# ========================================
# CONFIGURAÇÕES
# ========================================

PASTA_PROJETO = Path(__file__).resolve().parent

load_dotenv(PASTA_PROJETO / ".env")

app = Flask(__name__)

app.secret_key = os.environ.get(
    "SECRET_KEY",
    "crm_saas_segredo"
)

DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL não encontrada. Verifique o arquivo .env."
    )


# ========================================
# BANCO DE DADOS - SUPABASE POSTGRESQL
# ========================================

def conectar_banco():
    return psycopg.connect(
        DATABASE_URL,
        sslmode="require",
        connect_timeout=15
    )


# ========================================
# FUNÇÕES AUXILIARES
# ========================================

def converter_valor(valor):
    valor = str(valor).strip().replace(",", ".")
    numero = float(valor)

    if numero < 0:
        raise ValueError

    return numero


def verificar_login():
    return "usuario" in session


def obter_cliente(cursor, cliente_id, usuario):
    cursor.execute("""
        SELECT id, nome, telefone
        FROM clientes
        WHERE id = %s
        AND usuario = %s
    """, (cliente_id, usuario))

    return cursor.fetchone()


def validar_data_horario(data, horario):
    try:
        datetime.strptime(data, "%Y-%m-%d")
        datetime.strptime(horario, "%H:%M")
        return True
    except (ValueError, TypeError):
        return False


# ========================================
# DASHBOARD
# ========================================

@app.route("/")
def home():

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    usuario = session["usuario"]

    cursor.execute("""
        SELECT COUNT(*)
        FROM clientes
        WHERE usuario = %s
    """, (usuario,))

    total_clientes = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(valor), 0)
        FROM clientes
        WHERE usuario = %s
        AND tipo_valor = 'fixo'
    """, (usuario,))

    faturamento_fixo = cursor.fetchone()[0]

    cursor.execute("""
        SELECT COALESCE(SUM(valor), 0)
        FROM clientes
        WHERE usuario = %s
        AND tipo_valor = 'mensal'
    """, (usuario,))

    faturamento_mensal = cursor.fetchone()[0]

    faturamento = faturamento_fixo + faturamento_mensal

    cursor.execute("""
        SELECT nome, valor
        FROM clientes
        WHERE usuario = %s
        ORDER BY id DESC
        LIMIT 5
    """, (usuario,))

    ultimos_clientes = cursor.fetchall()

    hoje = datetime.now().strftime("%Y-%m-%d")

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE usuario = %s
        AND data = %s
        AND status = 'agendado'
    """, (usuario, hoje))

    agendamentos_hoje = cursor.fetchone()[0]

    # ========================================
    # FINANCEIRO DOS AGENDAMENTOS
    # ========================================

    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(valor), 0)
        FROM agendamentos
        WHERE usuario = %s AND status = 'concluido'
    """, (usuario,))

    total_concluidos, faturamento_realizado = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*), COALESCE(SUM(valor), 0)
        FROM agendamentos
        WHERE usuario = %s AND status = 'agendado'
    """, (usuario,))

    total_pendentes, faturamento_pendente = cursor.fetchone()

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE usuario = %s AND status = 'cancelado'
    """, (usuario,))

    total_cancelados = cursor.fetchone()[0]

    cursor.execute("""
        SELECT
            agendamentos.horario,
            clientes.nome,
            agendamentos.servico,
            agendamentos.status
        FROM agendamentos
        JOIN clientes
            ON clientes.id = agendamentos.cliente_id
        WHERE agendamentos.usuario = %s
        AND agendamentos.data = %s
        ORDER BY agendamentos.horario ASC
        LIMIT 5
    """, (usuario, hoje))

    proximos_agendamentos = cursor.fetchall()

    cursor.execute("""
        SELECT is_admin
        FROM usuarios
        WHERE usuario = %s
    """, (usuario,))

    dados_usuario = cursor.fetchone()

    dias_restantes = None

    if dados_usuario and dados_usuario[0] == 1:
        dias_restantes = "Administrador"

    conn.close()

    return render_template(
        "dashboard.html",
        total_clientes=total_clientes,
        faturamento=faturamento,
        faturamento_fixo=faturamento_fixo,
        faturamento_mensal=faturamento_mensal,
        ultimos_clientes=ultimos_clientes,
        agendamentos_hoje=agendamentos_hoje,
        proximos_agendamentos=proximos_agendamentos,
        usuario=usuario,
        dias_restantes=dias_restantes,
        total_concluidos=total_concluidos,
        faturamento_realizado=faturamento_realizado,
        total_pendentes=total_pendentes,
        faturamento_pendente=faturamento_pendente,
        total_cancelados=total_cancelados
    )


# ========================================
# CADASTRO DE CLIENTES
# ========================================

@app.route("/cadastro")
def cadastro():

    if not verificar_login():
        return redirect("/login")

    return render_template("cadastro.html")


@app.route("/cadastrar", methods=["POST"])
def cadastrar():

    if not verificar_login():
        return redirect("/login")

    nome = request.form.get("nome", "").strip()
    telefone = request.form.get("telefone", "")
    observacoes = request.form.get("observacoes", "")
    valor_digitado = request.form.get("valor", "0")
    tipo_valor = request.form.get("tipo_valor", "fixo")

    telefone = "".join(filter(str.isdigit, telefone))

    if not nome:
        flash("Informe o nome do cliente!", "erro")
        return redirect("/cadastro")

    if len(telefone) not in [10, 11]:
        flash("Telefone inválido!", "erro")
        return redirect("/cadastro")

    if tipo_valor not in ["fixo", "mensal"]:
        flash("Tipo de cobrança inválido!", "erro")
        return redirect("/cadastro")

    try:
        valor = converter_valor(valor_digitado)
    except (ValueError, TypeError):
        flash("Valor inválido!", "erro")
        return redirect("/cadastro")

    data_cadastro = datetime.now().strftime("%d/%m/%Y")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO clientes (
            nome,
            telefone,
            observacoes,
            data_cadastro,
            usuario,
            valor,
            tipo_valor
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s)
    """, (
        nome,
        telefone,
        observacoes,
        data_cadastro,
        session["usuario"],
        valor,
        tipo_valor
    ))

    conn.commit()
    conn.close()

    flash("Cliente cadastrado com sucesso!", "sucesso")
    return redirect("/clientes")


# ========================================
# LISTA DE CLIENTES
# ========================================

@app.route("/clientes")
def clientes():

    if not verificar_login():
        return redirect("/login")

    busca = request.args.get("busca", "").strip()

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            telefone,
            observacoes,
            data_cadastro,
            valor,
            usuario,
            tipo_valor
        FROM clientes
        WHERE usuario = %s
        AND nome ILIKE %s
        ORDER BY id DESC
    """, (
        session["usuario"],
        "%" + busca + "%"
    ))

    lista_clientes = cursor.fetchall()

    conn.close()

    return render_template(
        "clientes.html",
        clientes=lista_clientes,
        busca=busca
    )


# ========================================
# EXCLUIR CLIENTE
# ========================================

@app.route("/excluir/<int:id>", methods=["GET", "POST"])
def excluir(id):

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT COUNT(*)
        FROM agendamentos
        WHERE cliente_id = %s
        AND usuario = %s
    """, (id, session["usuario"]))

    possui_agendamentos = cursor.fetchone()[0]

    if possui_agendamentos:
        conn.close()

        flash(
            "Este cliente possui agendamentos. "
            "Gerencie os agendamentos antes de excluí-lo.",
            "erro"
        )

        return redirect("/clientes")

    cursor.execute("""
        DELETE FROM clientes
        WHERE id = %s
        AND usuario = %s
    """, (id, session["usuario"]))

    conn.commit()
    conn.close()

    flash("Cliente excluído com sucesso!", "sucesso")
    return redirect("/clientes")


# ========================================
# EDITAR CLIENTE
# ========================================

@app.route("/editar/<int:id>")
def editar(id):

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            telefone,
            observacoes,
            data_cadastro,
            valor,
            usuario,
            tipo_valor
        FROM clientes
        WHERE id = %s
        AND usuario = %s
    """, (id, session["usuario"]))

    cliente = cursor.fetchone()

    conn.close()

    if not cliente:
        return redirect("/clientes")

    return render_template(
        "editar.html",
        cliente=cliente
    )


# ========================================
# ATUALIZAR CLIENTE
# ========================================

@app.route("/atualizar/<int:id>", methods=["POST"])
def atualizar(id):

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            nome,
            telefone,
            observacoes,
            data_cadastro,
            valor,
            usuario,
            tipo_valor
        FROM clientes
        WHERE id = %s
        AND usuario = %s
    """, (id, session["usuario"]))

    cliente = cursor.fetchone()

    if not cliente:
        conn.close()
        return redirect("/clientes")

    nome = request.form.get("nome", cliente[1]).strip()
    telefone = request.form.get("telefone", cliente[2] or "")
    observacoes = request.form.get(
        "observacoes",
        cliente[3] or ""
    )

    valor_digitado = request.form.get(
        "valor",
        str(cliente[5] or 0)
    )

    tipo_valor = request.form.get(
        "tipo_valor",
        cliente[7] or "fixo"
    )

    telefone = "".join(filter(str.isdigit, telefone))

    if not nome:
        conn.close()
        flash("Informe o nome do cliente!", "erro")
        return redirect(f"/editar/{id}")

    if len(telefone) not in [10, 11]:
        conn.close()
        flash("Telefone inválido!", "erro")
        return redirect(f"/editar/{id}")

    if tipo_valor not in ["fixo", "mensal"]:
        conn.close()
        flash("Tipo de cobrança inválido!", "erro")
        return redirect(f"/editar/{id}")

    try:
        valor = converter_valor(valor_digitado)
    except (ValueError, TypeError):
        conn.close()
        flash("Valor inválido!", "erro")
        return redirect(f"/editar/{id}")

    cursor.execute("""
        UPDATE clientes
        SET
            nome = %s,
            telefone = %s,
            observacoes = %s,
            valor = %s,
            tipo_valor = %s
        WHERE id = %s
        AND usuario = %s
    """, (
        nome,
        telefone,
        observacoes,
        valor,
        tipo_valor,
        id,
        session["usuario"]
    ))

    conn.commit()
    conn.close()

    flash("Cliente atualizado com sucesso!", "sucesso")
    return redirect("/clientes")


# ========================================
# AGENDAMENTOS - LISTAGEM COMPLETA
# ========================================

@app.route("/agendamentos")
def agendamentos():

    if not verificar_login():
        return redirect("/login")

    data_filtro = request.args.get("data", "").strip()

    if data_filtro:
        try:
            datetime.strptime(data_filtro, "%Y-%m-%d")
        except ValueError:
            flash("Data inválida!", "erro")
            return redirect("/agendamentos")

    conn = conectar_banco()
    cursor = conn.cursor()

    consulta = """
        SELECT
            agendamentos.id,
            agendamentos.cliente_id,
            clientes.nome,
            clientes.telefone,
            agendamentos.servico,
            agendamentos.data,
            agendamentos.horario,
            agendamentos.valor,
            agendamentos.observacoes,
            agendamentos.status
        FROM agendamentos
        JOIN clientes
            ON clientes.id = agendamentos.cliente_id
        WHERE agendamentos.usuario = %s
    """

    parametros = [session["usuario"]]

    if data_filtro:
        consulta += " AND agendamentos.data = %s"
        parametros.append(data_filtro)

    consulta += """
        ORDER BY
            CASE
                WHEN agendamentos.data >= %s THEN 0
                ELSE 1
            END ASC,
            CASE
                WHEN agendamentos.data >= %s
                THEN agendamentos.data
            END ASC,
            CASE
                WHEN agendamentos.data < %s
                THEN agendamentos.data
            END DESC,
            agendamentos.horario ASC
    """

    hoje = datetime.now().strftime("%Y-%m-%d")

    parametros.extend([hoje, hoje, hoje])

    cursor.execute(consulta, parametros)

    lista_agendamentos = cursor.fetchall()

    cursor.execute("""
        SELECT id, nome
        FROM clientes
        WHERE usuario = %s
        ORDER BY nome ASC
    """, (session["usuario"],))

    lista_clientes = cursor.fetchall()

    conn.close()

    return render_template(
        "agendamentos.html",
        agendamentos=lista_agendamentos,
        clientes=lista_clientes,
        data_filtro=data_filtro,
        data_selecionada=data_filtro
    )


# ========================================
# NOVO AGENDAMENTO
# ========================================

@app.route("/novo_agendamento")
def novo_agendamento():

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, nome
        FROM clientes
        WHERE usuario = %s
        ORDER BY nome ASC
    """, (session["usuario"],))

    lista_clientes = cursor.fetchall()

    conn.close()

    return render_template(
        "novo_agendamento.html",
        clientes=lista_clientes
    )


# ========================================
# CADASTRAR AGENDAMENTO
# ========================================

@app.route("/cadastrar_agendamento", methods=["POST"])
def cadastrar_agendamento():

    if not verificar_login():
        return redirect("/login")

    cliente_id = request.form.get("cliente_id", type=int)
    servico = request.form.get("servico", "").strip()
    data = request.form.get("data", "").strip()
    horario = request.form.get("horario", "").strip()
    valor_digitado = request.form.get("valor", "0")
    observacoes = request.form.get(
        "observacoes", ""
    ).strip()

    if not cliente_id:
        flash("Selecione um cliente!", "erro")
        return redirect("/novo_agendamento")

    if not servico:
        flash("Informe o serviço!", "erro")
        return redirect("/novo_agendamento")

    if not validar_data_horario(data, horario):
        flash("Data ou horário inválido!", "erro")
        return redirect("/novo_agendamento")

    try:
        valor = converter_valor(valor_digitado)
    except (ValueError, TypeError):
        flash("Informe um valor válido!", "erro")
        return redirect("/novo_agendamento")

    conn = conectar_banco()
    cursor = conn.cursor()

    cliente = obter_cliente(
        cursor,
        cliente_id,
        session["usuario"]
    )

    if not cliente:
        conn.close()
        flash("Cliente não encontrado!", "erro")
        return redirect("/novo_agendamento")

    cursor.execute("""
        SELECT id
        FROM agendamentos
        WHERE usuario = %s
        AND data = %s
        AND horario = %s
        AND status = 'agendado'
    """, (session["usuario"], data, horario))

    horario_ocupado = cursor.fetchone()

    if horario_ocupado:
        conn.close()
        flash(
            "Já existe um agendamento nesse horário!",
            "erro"
        )
        return redirect("/novo_agendamento")

    cursor.execute("""
        INSERT INTO agendamentos (
            cliente_id,
            usuario,
            servico,
            data,
            horario,
            valor,
            observacoes,
            status,
            data_criacao
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        cliente_id,
        session["usuario"],
        servico,
        data,
        horario,
        valor,
        observacoes,
        "agendado",
        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ))

    conn.commit()
    conn.close()

    flash("Agendamento criado com sucesso!", "sucesso")

    return redirect("/agendamentos?data=" + data)


# ========================================
# EDITAR AGENDAMENTO
# ========================================

@app.route("/editar_agendamento/<int:id>")
def editar_agendamento(id):

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            id,
            cliente_id,
            servico,
            data,
            horario,
            valor,
            observacoes,
            status
        FROM agendamentos
        WHERE id = %s
        AND usuario = %s
    """, (id, session["usuario"]))

    agendamento = cursor.fetchone()

    cursor.execute("""
        SELECT id, nome
        FROM clientes
        WHERE usuario = %s
        ORDER BY nome ASC
    """, (session["usuario"],))

    lista_clientes = cursor.fetchall()

    conn.close()

    if not agendamento:
        flash("Agendamento não encontrado!", "erro")
        return redirect("/agendamentos")

    return render_template(
        "editar_agendamento.html",
        agendamento=agendamento,
        clientes=lista_clientes
    )


# ========================================
# ATUALIZAR AGENDAMENTO
# ========================================

@app.route("/atualizar_agendamento/<int:id>", methods=["POST"])
def atualizar_agendamento(id):

    if not verificar_login():
        return redirect("/login")

    cliente_id = request.form.get("cliente_id", type=int)
    servico = request.form.get("servico", "").strip()
    data = request.form.get("data", "").strip()
    horario = request.form.get("horario", "").strip()
    valor_digitado = request.form.get("valor", "0")
    observacoes = request.form.get(
        "observacoes", ""
    ).strip()
    status = request.form.get("status", "agendado")

    if status not in [
        "agendado",
        "concluido",
        "cancelado"
    ]:
        flash("Status inválido!", "erro")
        return redirect(f"/editar_agendamento/{id}")

    if not cliente_id or not servico:
        flash(
            "Preencha os campos obrigatórios!",
            "erro"
        )
        return redirect(f"/editar_agendamento/{id}")

    if not validar_data_horario(data, horario):
        flash("Data ou horário inválido!", "erro")
        return redirect(f"/editar_agendamento/{id}")

    try:
        valor = converter_valor(valor_digitado)
    except (ValueError, TypeError):
        flash("Informe um valor válido!", "erro")
        return redirect(f"/editar_agendamento/{id}")

    conn = conectar_banco()
    cursor = conn.cursor()

    cliente = obter_cliente(
        cursor,
        cliente_id,
        session["usuario"]
    )

    if not cliente:
        conn.close()
        flash("Cliente não encontrado!", "erro")
        return redirect(f"/editar_agendamento/{id}")

    cursor.execute("""
        SELECT id
        FROM agendamentos
        WHERE usuario = %s
        AND data = %s
        AND horario = %s
        AND status = 'agendado'
        AND id != %s
    """, (
        session["usuario"],
        data,
        horario,
        id
    ))

    horario_ocupado = cursor.fetchone()

    if horario_ocupado and status == "agendado":
        conn.close()
        flash(
            "Já existe um agendamento nesse horário!",
            "erro"
        )
        return redirect(f"/editar_agendamento/{id}")

    cursor.execute("""
        UPDATE agendamentos
        SET
            cliente_id = %s,
            servico = %s,
            data = %s,
            horario = %s,
            valor = %s,
            observacoes = %s,
            status = %s
        WHERE id = %s
        AND usuario = %s
    """, (
        cliente_id,
        servico,
        data,
        horario,
        valor,
        observacoes,
        status,
        id,
        session["usuario"]
    ))

    conn.commit()
    conn.close()

    flash(
        "Agendamento atualizado com sucesso!",
        "sucesso"
    )

    return redirect("/agendamentos?data=" + data)


# ========================================
# ATUALIZAR STATUS DO AGENDAMENTO
# ========================================

@app.route(
    "/status_agendamento/<int:id>",
    methods=["POST"]
)
def status_agendamento(id):

    if not verificar_login():
        return redirect("/login")

    status = request.form.get("status", "")

    if status not in [
        "agendado",
        "concluido",
        "cancelado"
    ]:
        flash("Status inválido!", "erro")
        return redirect("/agendamentos")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE agendamentos
        SET status = %s
        WHERE id = %s
        AND usuario = %s
    """, (
        status,
        id,
        session["usuario"]
    ))

    conn.commit()
    conn.close()

    flash("Status atualizado!", "sucesso")
    return redirect("/agendamentos")


# ========================================
# EXCLUIR AGENDAMENTO
# ========================================

@app.route(
    "/excluir_agendamento/<int:id>",
    methods=["POST"]
)
def excluir_agendamento(id):

    if not verificar_login():
        return redirect("/login")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        DELETE FROM agendamentos
        WHERE id = %s
        AND usuario = %s
    """, (
        id,
        session["usuario"]
    ))

    conn.commit()
    conn.close()

    flash("Agendamento excluído!", "sucesso")
    return redirect("/agendamentos")


# ========================================
# LOGIN
# ========================================

@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/fazer_login", methods=["POST"])
def fazer_login():

    usuario = request.form.get("usuario", "")
    senha = request.form.get("senha", "")

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT usuario, senha, is_admin
        FROM usuarios
        WHERE usuario = %s
    """, (usuario,))

    usuario_encontrado = cursor.fetchone()

    conn.close()

    if usuario_encontrado:

        senha_salva = usuario_encontrado[1]

        if senha_salva and check_password_hash(
            senha_salva, senha
        ):

            session.clear()

            session["usuario"] = usuario_encontrado[0]
            session["is_admin"] = usuario_encontrado[2]

            return redirect("/")

    flash("Usuário ou senha incorretos.", "erro")
    return redirect("/login")


# ========================================
# LOGOUT
# ========================================

@app.route("/logout")
def logout():

    session.clear()
    return redirect("/login")


# ========================================
# CADASTRO DE USUÁRIOS
# ========================================

@app.route(
    "/cadastrar_usuario",
    methods=["POST"]
)
def cadastrar_usuario():

    usuario = request.form.get(
        "usuario", ""
    ).strip()

    email = request.form.get(
        "email", ""
    ).strip()

    senha = request.form.get("senha", "")

    if not usuario or not email or not senha:
        flash(
            "Preencha todos os campos!",
            "erro"
        )
        return redirect("/cadastro_usuario")

    senha_hash = generate_password_hash(senha)

    conn = conectar_banco()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id
        FROM usuarios
        WHERE LOWER(email) = LOWER(%s)
    """, (email,))

    email_existente = cursor.fetchone()

    if email_existente:
        conn.close()

        flash(
            "Este e-mail já está cadastrado.",
            "erro"
        )

        return redirect("/cadastro_usuario")

    try:
        cursor.execute("""
            INSERT INTO usuarios (
                usuario,
                email,
                senha,
                is_admin,
                plano_ativo
            )
            VALUES (%s, %s, %s, %s, %s)
        """, (
            usuario,
            email,
            senha_hash,
            0,
            0
        ))

        conn.commit()

    except psycopg.IntegrityError:
        conn.rollback()
        conn.close()

        flash(
            "Este nome de usuário já está em uso.",
            "erro"
        )

        return redirect("/cadastro_usuario")

    conn.close()

    flash(
        "Conta criada com sucesso! Faça login.",
        "sucesso"
    )

    return redirect("/login")


@app.route("/cadastro_usuario")
def cadastro_usuario():
    return render_template("cadastro_usuario.html")


# ========================================
# EXECUÇÃO
# ========================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
