from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import FileResponse
import uvicorn
import json
import requests
import time
import psycopg2 # ❗️ MUDANÇA: Sai MySQL, entra PostgreSQL
from psycopg2 import sql, extras
from pydantic import BaseModel
from typing import List
import os # ❗️ NOVO: Para ler as Variáveis de Ambiente

# Cria a aplicação
app = FastAPI()

# --- CONFIGURAÇÕES LIDAS DO AMBIENTE (Render vai preencher isto) ---
DATABASE_URL = os.environ.get("postgresql://bot_admin_db_user:97fBcDLeJfywc6Sl1uWu5PIQwnJriLk4@dpg-d44fn9muk2gs73clmee0-a.oregon-postgres.render.com/bot_admin_db")
ACCESS_TOKEN = os.environ.get("ACCESS_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
MEU_TOKEN_SECRETO = os.environ.get("MEU_TOKEN_SECRETO")

# --- ESTADOS EM MEMÓRIA ---
user_states = {}

# --- MODELOS DE DADOS (Pydantic) ---
class OpcaoMenu(BaseModel):
    numero_opcao: str
    titulo_opcao: str
    texto_resposta: str

class BotConfig(BaseModel):
    mensagem_boas_vindas: str
    opcoes_menu: List[OpcaoMenu]

# --- FUNÇÃO 1: SETUP DO BANCO (Adaptada para PostgreSQL) ---
def setup_database():
    """Cria as tabelas e insere os dados de exemplo no PostgreSQL, se não existirem."""
    conn = None
    cursor = None
    
    # ❗️ MUDANÇA: Conecta usando a URL do Render
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()

        # ❗️ MUDANÇA: Sintaxe SQL do PostgreSQL
        sql_create_bots_table = """
        CREATE TABLE IF NOT EXISTS bots (
            id SERIAL PRIMARY KEY,
            bot_id VARCHAR(50) UNIQUE NOT NULL,
            nome_cliente VARCHAR(100),
            mensagem_boas_vindas TEXT
        );
        """
        
        sql_create_opcoes_menu_table = """
        CREATE TABLE IF NOT EXISTS opcoes_menu (
            id SERIAL PRIMARY KEY,
            bot_id VARCHAR(50) NOT NULL REFERENCES bots(bot_id) ON DELETE CASCADE,
            numero_opcao VARCHAR(20) NOT NULL,
            titulo_opcao VARCHAR(100) NOT NULL,
            texto_resposta TEXT NOT NULL,
            UNIQUE (bot_id, numero_opcao)
        );
        """
        
        cursor.execute(sql_create_bots_table)
        print(">>> Tabela 'bots' verificada/criada.")
        cursor.execute(sql_create_opcoes_menu_table)
        print(">>> Tabela 'opcoes_menu' verificada/criada.")
        
        # ❗️ MUDANÇA: Sintaxe de "INSERT ... ON CONFLICT" do PostgreSQL
        sql_insert_bot = """
        INSERT INTO bots (bot_id, nome_cliente, mensagem_boas_vindas)
        VALUES ('pizzaria_vitor', 'Pizzaria do Vitor', 'Olá! 🍕 Bem-vindo à Pizzaria Bot!\n\nDigite o *número* da opção desejada:')
        ON CONFLICT (bot_id) DO UPDATE SET
            nome_cliente = EXCLUDED.nome_cliente,
            mensagem_boas_vindas = EXCLUDED.mensagem_boas_vindas;
        """
        
        sql_insert_opcoes = """
        INSERT INTO opcoes_menu (bot_id, numero_opcao, titulo_opcao, texto_resposta)
        VALUES
            ('pizzaria_vitor', '1', 'Ver Cardápio 📖', 'Nosso cardápio (simplificado):\n\n*Pizzas Salgadas (G - R$ 50,00):*\n- Calabresa\n- Mussarela\n- Portuguesa\n\n*Bebidas (R$ 10,00):*\n- Coca-Cola 2L\n- Guaraná 2L\n\nPara voltar, digite *menu*.'),
            ('pizzaria_vitor', '2', 'Fazer um pedido 📝', 'Ótimo! Por favor, escreva seu pedido completo.\n(Ex: 1 pizza calabresa G, 1 Coca 2L)\n\nSe mudar de ideia, digite *cancelar*.'),
            ('pizzaria_vitor', '3', 'Falar com um atendente 🙋', 'Tudo bem, um de nossos atendentes humanos irá assumir a conversa em breve. Por favor, aguarde.'),
            ('pizzaria_vitor', '4', '(PROMOÇÃO) Ver nosso endereço 📍', 'Nossa pizzaria fica na Rua da Inteligência Artificial, nº 123. 🤖')
        ON CONFLICT (bot_id, numero_opcao) DO UPDATE SET
            titulo_opcao = EXCLUDED.titulo_opcao,
            texto_resposta = EXCLUDED.texto_resposta;
        """
        
        cursor.execute(sql_insert_bot)
        cursor.execute(sql_insert_opcoes)
        print(">>> Dados de exemplo da 'pizzaria_vitor' inseridos/atualizados.")
        
        conn.commit()

    except (Exception, psycopg2.DatabaseError) as e:
        print(f">>> ERRO GRAVE no setup do banco de dados (PostgreSQL): {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- FUNÇÃO 2: BUSCAR CONFIGURAÇÕES (Adaptada para PostgreSQL) ---
def get_bot_config(bot_id="pizzaria_vitor"):
    """Busca a config dinâmica do bot (boas-vindas e opções) do PostgreSQL."""
    conn = None
    cursor = None
    config_data = {
        "mensagem_boas_vindas": "",
        "opcoes_menu": []
    }
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor) # Retorna resultados como dicionários

        query_bot = "SELECT mensagem_boas_vindas FROM bots WHERE bot_id = %s"
        cursor.execute(query_bot, (bot_id,))
        bot_info = cursor.fetchone()
        
        if bot_info:
            config_data["mensagem_boas_vindas"] = bot_info["mensagem_boas_vindas"]
        else:
            print(f">>> ERRO: Bot ID '{bot_id}' não encontrado na tabela 'bots'.")
            return None

        query_opcoes = "SELECT numero_opcao, titulo_opcao, texto_resposta FROM opcoes_menu WHERE bot_id = %s ORDER BY numero_opcao ASC"
        cursor.execute(query_opcoes, (bot_id,))
        opcoes_info = cursor.fetchall()
        
        config_data["opcoes_menu"] = [dict(row) for row in opcoes_info]
        return config_data
        
    except (Exception, psycopg2.DatabaseError) as e:
        print(f">>> ERRO ao buscar configurações no PostgreSQL: {e}")
        return None
    finally:
        if cursor: cursor.close()
        if conn: conn.close()

# --- FUNÇÃO 3: ENVIAR MENSAGEM (Sem mudanças, mas usa ACCESS_TOKEN do ambiente) ---
def enviar_mensagem_whatsapp(para_numero, texto_da_mensagem):
    """Envia uma mensagem de texto para um número do WhatsApp."""
    print(f">>> Enviando resposta para {para_numero}...")
    url_api = f"https://graph.facebook.com/v20.0/{PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {ACCESS_TOKEN}", # Lê do ambiente
        "Content-Type": "application/json",
    }
    data = {
        "messaging_product": "whatsapp",
        "to": para_numero,
        "type": "text",
        "text": {"body": texto_da_mensagem},
    }
    try:
        response = requests.post(url_api, headers=headers, json=data)
        response.raise_for_status() 
        print(f">>> Resposta da API: {response.json()}")
        return True
    except requests.exceptions.RequestException as e:
        print(f">>> ERRO ao enviar mensagem: {e}")
        if e.response is not None:
            print(f">>> Detalhes da resposta: {e.response.text}")
        return False

# --- FUNÇÃO 4: LÓGICA DO BOT (Sem mudanças na lógica) ---
def processar_logica_bot(numero_do_cliente, texto_da_mensagem, bot_id):
    """Decide o que responder com base no estado e nas configs DINÂMICAS do PostgreSQL."""
    
    config = get_bot_config(bot_id)
    if not config:
        print(f">>> FALHA: Não foi possível carregar a config do bot '{bot_id}'.")
        enviar_mensagem_whatsapp(numero_do_cliente, "Desculpe, estou com um problema interno. Tente novamente mais tarde.")
        return

    MSG_BOAS_VINDAS = config["mensagem_boas_vindas"]
    OPCOES_MENU_DB = config["opcoes_menu"] 
    
    menu_texto_dinamico = MSG_BOAS_VINDAS + "\n\n"
    opcoes_validas = {} 
    
    for opcao in OPCOES_MENU_DB:
        num = opcao["numero_opcao"]
        titulo = opcao["titulo_opcao"]
        resposta = opcao["texto_resposta"]
        menu_texto_dinamico += f"*{num}.* {titulo}\n"
        
        # Mapeia as ações (Ex: o '2' é especial)
        if num == "2": 
            opcoes_validas[num] = {"tipo": "iniciar_pedido", "resposta": resposta}
        elif num == "3": 
            opcoes_validas[num] = {"tipo": "atendente", "resposta": resposta}
        else: 
            opcoes_validas[num] = {"tipo": "texto_simples", "resposta": resposta}

    
    texto_limpo = texto_da_mensagem.lower().strip()
    
    if texto_limpo in ["menu", "cancelar", "sair"]:
        user_states.pop(numero_do_cliente, None) 
        print(f">>> [RESET] Conversa resetada para {numero_do_cliente}.")
        enviar_mensagem_whatsapp(numero_do_cliente, menu_texto_dinamico)
        user_states[numero_do_cliente] = "menu_principal"
        return

    estado_atual = user_states.get(numero_do_cliente)

    if estado_atual == "fazendo_pedido":
        pedido = texto_da_mensagem 
        time.sleep(1) 
        enviar_mensagem_whatsapp(numero_do_cliente, f"✅ Pedido anotado!\n\n*Seu pedido foi:*\n'{pedido}'\n\nLogo um atendente confirmará. Obrigado!")
        time.sleep(1)
        enviar_mensagem_whatsapp(numero_do_cliente, "Se precisar de algo mais, é só mandar 'oi' ou 'menu' para ver as opções novamente.")
        user_states.pop(numero_do_cliente, None)
        return

    elif estado_atual == "menu_principal":
        if texto_limpo in opcoes_validas:
            opcao_escolhida = opcoes_validas[texto_limpo]
            tipo = opcao_escolhida["tipo"]
            resposta_bot = opcao_escolhida["resposta"]
            
            if tipo == "iniciar_pedido":
                enviar_mensagem_whatsapp(numero_do_cliente, resposta_bot)
                user_states[numero_do_cliente] = "fazendo_pedido"
            elif tipo == "atendente":
                enviar_mensagem_whatsapp(numero_do_cliente, resposta_bot)
                user_states.pop(numero_do_cliente, None)
            else: 
                enviar_mensagem_whatsapp(numero_do_cliente, resposta_bot)
                time.sleep(1)
                enviar_mensagem_whatsapp(numero_do_cliente, "Digite 'menu' para voltar ao início.")
                user_states.pop(numero_do_cliente, None)
        else:
            enviar_mensagem_whatsapp(numero_do_cliente, "Opção inválida. 😕\nPor favor, digite *apenas o número* da opção.")
            time.sleep(1)
            enviar_mensagem_whatsapp(numero_do_cliente, menu_texto_dinamico)
        return
    else: 
        enviar_mensagem_whatsapp(numero_do_cliente, menu_texto_dinamico)
        user_states[numero_do_cliente] = "menu_principal"
        return

# --- ROTAS DO WEBHOOK (Sem mudanças) ---
@app.get("/webhook-pizzaria")
async def verificar_webhook(request: Request):
    """Verifica o token do Webhook da Meta."""
    print(">>> [GET] Recebendo requisição de VERIFICAÇÃO...")
    params = request.query_params
    challenge = params.get("hub.challenge")
    token_recebido = params.get("hub.verify_token")
    if token_recebido == MEU_TOKEN_SECRETO: # Lê do ambiente
        print(">>> [GET] Token verificado com sucesso!")
        return int(challenge)
    else:
        print(f">>> [GET] ERRO: Token de verificação não bate!")
        return {"status": "erro de token"}, 403

@app.post("/webhook-pizzaria")
async def receber_mensagem(request: Request):
    """Recebe as mensagens dos usuários (POST) e chama a lógica do bot."""
    dados_json = await request.json()
    print("\n--- [POST] MENSAGEM RECEBIDA ---")
    print(json.dumps(dados_json, indent=2))
    
    try:
        change = dados_json["entry"][0]["changes"][0]
        if change["field"] == "messages" and "messages" in change["value"]:
            mensagem_info = change["value"]["messages"][0]
            numero_do_cliente = mensagem_info["from"]
            
            # ❗️ MUDANÇA: O bot_id agora pode vir do 'phone_number_id'
            # (Mas ainda deixamos 'pizzaria_vitor' como padrão)
            metadata = change["value"]["metadata"]
            phone_id_recebido = metadata["phone_number_id"]
            
            # Lógica futura:
            # if phone_id_recebido == "12345":
            #     bot_id_do_cliente = "pizzaria_vitor"
            # elif phone_id_recebido == "67890":
            #     bot_id_do_cliente = "advogado_joao"
            bot_id_do_cliente = "pizzaria_vitor" # Fixo por enquanto
            
            if "text" in mensagem_info:
                texto_da_mensagem = mensagem_info["text"]["body"]
                print(f">>> Mensagem de '{numero_do_cliente}': '{texto_da_mensagem}'")
                processar_logica_bot(numero_do_cliente, texto_da_mensagem, bot_id_do_cliente)
            else:
                enviar_mensagem_whatsapp(numero_do_cliente, "Desculpe, eu só entendo mensagens de texto no momento. 😅")

    except Exception as e:
        print(f">>> ERRO GRAVE ao processar a mensagem: {e}")
        pass 
    print("---------------------------------\n")
    return {"status": "recebido"}


# --- ROTAS DO PAINEL ADMIN (Adaptadas para PostgreSQL) ---
@app.get("/admin")
async def get_admin_page():
    """Serve a página HTML do painel admin."""
    print(">>> [ADMIN] Servindo a página admin.html...")
    return FileResponse("admin.html")

@app.get("/api/bot/{bot_id}")
async def get_bot_data(bot_id: str):
    """API para o painel admin carregar as configs do bot."""
    print(f">>> [API GET] Carregando dados para o bot_id: {bot_id}")
    config = get_bot_config(bot_id)
    if not config:
        raise HTTPException(status_code=404, detail="Bot não encontrado")
    return config

@app.post("/api/bot/{bot_id}")
async def update_bot_data(bot_id: str, config: BotConfig):
    """API para o painel admin salvar as novas configs do bot no PostgreSQL."""
    print(f">>> [API POST] Salvando dados para o bot_id: {bot_id}")
    conn = None
    cursor = None
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cursor = conn.cursor()
        
        conn.autocommit = False # Inicia a transação
        
        sql_update_bot = "UPDATE bots SET mensagem_boas_vindas = %s WHERE bot_id = %s"
        cursor.execute(sql_update_bot, (config.mensagem_boas_vindas, bot_id))
        
        sql_delete_opcoes = "DELETE FROM opcoes_menu WHERE bot_id = %s"
        cursor.execute(sql_delete_opcoes, (bot_id,))
        
        sql_insert_opcao = """
        INSERT INTO opcoes_menu (bot_id, numero_opcao, titulo_opcao, texto_resposta)
        VALUES (%s, %s, %s, %s)
        """
        
        novas_opcoes_data = [
            (bot_id, opcao.numero_opcao, opcao.titulo_opcao, opcao.texto_resposta)
            for opcao in config.opcoes_menu
        ]
            
        if novas_opcoes_data:
            extras.execute_batch(cursor, sql_insert_opcao, novas_opcoes_data)
        
        conn.commit() # Salva a transação
        
        print(f">>> [API POST] Dados do bot '{bot_id}' salvos com sucesso!")
        return {"status": "sucesso"}
        
    except (Exception, psycopg2.DatabaseError) as e:
        if conn: conn.rollback() # Desfaz tudo se der erro
        print(f">>> ERRO ao salvar no PostgreSQL: {e}")
        raise HTTPException(status_code=500, detail=f"Erro de banco de dados: {e}")
    finally:
        if cursor: cursor.close()
        if conn: conn.close()


# --- RODA O SERVIDOR (Webhook + Admin) ---
@app.on_event("startup")
async def startup_event():
    """No startup, verifica o banco de dados."""
    print(">>> (Passo 1/2) Aplicação iniciando...")
    if not DATABASE_URL:
        print(">>> ERRO FATAL: Variável de ambiente DATABASE_URL não definida.")
        return
    if not ACCESS_TOKEN:
        print(">>> AVISO: Variável de ambiente ACCESS_TOKEN não definida.")
    
    print(">>> Verificando e configurando o banco de dados PostgreSQL...")
    setup_database()
    print(">>> Configuração do banco de dados concluída.")
    print(">>> (Passo 2/2) Aplicação pronta.")

if __name__ == "__main__":
    # Esta parte é só para testes locais (ex: python bot_pizzaria_v7_postgres.py)
    # Você precisaria definir as variáveis de ambiente no seu terminal primeiro
    # ex: export DATABASE_URL="postgresql://user:pass@host/db"
    # ex: export ACCESS_TOKEN="EAA..."
    print(">>> Rodando em modo de desenvolvimento local (use 'gunicorn' para produção)...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
