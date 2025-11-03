from fastapi import FastAPI, Request
import uvicorn
import json # Importamos json para formatar a saída

# Cria a aplicação
app = FastAPI()

# --- ETAPA DE VERIFICAÇÃO DO WEBHOOK (GET) ---
# O WhatsApp/Meta vai usar isso SÓ UMA VEZ para verificar se a sua URL é real.
@app.get("/webhook-pizzaria")
async def verificar_webhook(request: Request):
    print(">>> [GET] Recebendo requisição de VERIFICAÇÃO...")

    # Este token tem que ser EXATAMENTE IGUAL ao que vamos por no painel da Meta
    MEU_TOKEN_SECRETO = "senha123" 

    params = request.query_params
    challenge = params.get("hub.challenge")
    token_recebido = params.get("hub.verify_token")

    if token_recebido == MEU_TOKEN_SECRETO:
        print(">>> [GET] Token verificado com sucesso!")
        # A API da Meta espera um inteiro, não uma string
        return int(challenge) 
    else:
        print(f">>> [GET] ERRO: Token de verificação não bate! Recebido: {token_recebido}")
        return {"status": "erro de token"}, 403

# --- ETAPA DE RECEBIMENTO DE MENSAGENS (POST) ---
# É aqui que vamos receber as mensagens dos clientes DE VERDADE.
@app.post("/webhook-pizzaria")
async def receber_mensagem(request: Request):
    dados_json = await request.json()

    # Apenas imprime o que recebemos no terminal de forma bonita
    print("\n--- [POST] MENSAGEM RECEBIDA ---")
    print(json.dumps(dados_json, indent=2)) # json.dumps formata o JSON
    print("---------------------------------\n")

    # Responde 200 (OK) para o WhatsApp saber que recebemos
    return {"status": "recebido"}

# --- Roda o servidor ---
if __name__ == "__main__":
    print(">>> Servidor do bot iniciando na porta 8000...")
    uvicorn.run(app, host="0.0.0.0", port=8000)