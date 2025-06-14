# /// script
# dependencies = ["fastmcp", "httpx"]
# ///

"""
WAHA WhatsApp MCP Server - Versão Simples
------------------------------------------
Uma versão simplificada do servidor MCP para WAHA com as funcionalidades essenciais.

Configure a URL do servidor WAHA:
WAHA_BASE_URL=http://localhost:3000

Ou modifique a variável BASE_URL no código abaixo.
"""

import httpx
from fastmcp import FastMCP

# Configurações
BASE_URL = "http://localhost:3000"
DEFAULT_SESSION = "default"

# Criar servidor MCP
mcp = FastMCP("WAHA WhatsApp Simple")


def format_chat_id(phone_or_id: str) -> str:
    """Formatar ID do chat para WhatsApp"""
    if "@" in phone_or_id:
        return phone_or_id
    return f"{phone_or_id}@c.us"


@mcp.tool
def send_message(phone_number: str, message: str, session: str = DEFAULT_SESSION) -> str:
    """Enviar mensagem de texto para um número do WhatsApp"""
    chat_id = format_chat_id(phone_number)
    
    payload = {
        "chatId": chat_id,
        "text": message,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{BASE_URL}/api/sendText",
            json=payload
        )
        response.raise_for_status()
        return f"Mensagem enviada para {phone_number}: {message}"


@mcp.tool
def get_session_status(session: str = DEFAULT_SESSION) -> str:
    """Verificar status da sessão do WhatsApp"""
    with httpx.Client() as client:
        response = client.get(f"{BASE_URL}/api/sessions/{session}")
        if response.status_code == 200:
            data = response.json()
            return f"Sessão {session}: {data.get('status', 'unknown')}"
        else:
            return f"Erro ao verificar sessão {session}"


@mcp.tool
def start_whatsapp_session(session: str = DEFAULT_SESSION) -> str:
    """Iniciar sessão do WhatsApp"""
    with httpx.Client() as client:
        response = client.post(f"{BASE_URL}/api/sessions/{session}/start")
        if response.status_code == 201:
            return f"Sessão {session} iniciada com sucesso"
        else:
            return f"Erro ao iniciar sessão {session}"


@mcp.tool
def get_qr_code_for_whatsapp(session: str = DEFAULT_SESSION) -> str:
    """Obter código QR para autenticação do WhatsApp"""
    with httpx.Client() as client:
        response = client.get(f"{BASE_URL}/api/{session}/auth/qr")
        if response.status_code == 200:
            data = response.json()
            return f"QR Code: {data.get('value', 'Não disponível')}"
        else:
            return f"Erro ao obter QR code para sessão {session}"


@mcp.tool
def check_phone_number(phone_number: str, session: str = DEFAULT_SESSION) -> str:
    """Verificar se um número está registrado no WhatsApp"""
    with httpx.Client() as client:
        response = client.get(
            f"{BASE_URL}/api/checkNumberStatus",
            params={"phone": phone_number, "session": session}
        )
        if response.status_code == 200:
            data = response.json()
            exists = data.get("numberExists", False)
            return f"Número {phone_number}: {'Registrado' if exists else 'Não registrado'} no WhatsApp"
        else:
            return f"Erro ao verificar número {phone_number}"


@mcp.tool
def get_my_chats(session: str = DEFAULT_SESSION) -> str:
    """Obter lista dos meus chats"""
    with httpx.Client() as client:
        response = client.get(f"{BASE_URL}/api/{session}/chats")
        if response.status_code == 200:
            chats = response.json()
            chat_list = []
            for chat in chats[:10]:  # Limitar a 10 chats
                name = chat.get("name", "Sem nome")
                chat_id = chat.get("id", "")
                chat_list.append(f"- {name} ({chat_id})")
            return f"Seus chats:\n" + "\n".join(chat_list)
        else:
            return f"Erro ao obter chats da sessão {session}"


if __name__ == "__main__":
    mcp.run()
