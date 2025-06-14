# /// script
# dependencies = ["fastmcp", "httpx", "pydantic", "pydantic-settings"]
# ///

"""
FastMCP WAHA Server
------------------
Este servidor MCP fornece integração com WAHA (WhatsApp HTTP API),
permitindo controlar sessões do WhatsApp e enviar mensagens.

Para usar este servidor, configure as seguintes variáveis de ambiente:
WAHA_BASE_URL=http://localhost:3000  # URL do seu servidor WAHA
WAHA_API_KEY=your_api_key            # Chave da API (se necessário)
WAHA_DEFAULT_SESSION=default         # Sessão padrão para usar

Ou crie um arquivo .env com essas configurações.
"""

import base64
from typing import Annotated, Dict, List, Optional, Any
from enum import Enum

import httpx
from pydantic import BaseModel, Field, BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastmcp import FastMCP


class WAHASettings(BaseSettings):
    """Configurações para o servidor WAHA"""
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_prefix="WAHA_", env_file=".env"
    )

    base_url: str = "http://localhost:3000"
    api_key: Optional[str] = None
    default_session: str = "default"


class SessionStatus(str, Enum):
    """Status da sessão"""
    STOPPED = "STOPPED"
    STARTING = "STARTING" 
    SCAN_QR_CODE = "SCAN_QR_CODE"
    WORKING = "WORKING"
    FAILED = "FAILED"


class MessageType(str, Enum):
    """Tipos de mensagem"""
    TEXT = "text"
    IMAGE = "image"
    VIDEO = "video"
    AUDIO = "audio"
    VOICE = "voice"
    DOCUMENT = "document"
    STICKER = "sticker"


class ChatType(str, Enum):
    """Tipos de chat"""
    INDIVIDUAL = "individual"
    GROUP = "group"
    BROADCAST = "broadcast"


class SessionInfo(BaseModel):
    """Informações da sessão"""
    name: str
    status: SessionStatus
    me: Optional[Dict[str, Any]] = None


class MessageRequest(BaseModel):
    """Request para enviar mensagem"""
    chatId: str = Field(description="ID do chat (número com @c.us ou ID do grupo)")
    text: str = Field(description="Texto da mensagem")
    session: Optional[str] = None
    reply_to: Optional[str] = None


class MediaRequest(BaseModel):
    """Request para enviar mídia"""
    chatId: str = Field(description="ID do chat")
    file: Dict[str, Any] = Field(description="Arquivo para enviar")
    caption: Optional[str] = None
    session: Optional[str] = None


# Criar servidor MCP
mcp = FastMCP("WAHA WhatsApp Server")
settings = WAHASettings()


def get_headers() -> Dict[str, str]:
    """Obter headers para requisições"""
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def format_chat_id(phone_or_id: str) -> str:
    """Formatar ID do chat"""
    if "@" in phone_or_id:
        return phone_or_id
    if phone_or_id.endswith("@g.us"):
        return phone_or_id
    # Assumir que é um número de telefone
    return f"{phone_or_id}@c.us"


# ==========================================
# FERRAMENTAS DE SESSÃO
# ==========================================

@mcp.tool
def list_sessions() -> List[Dict[str, Any]]:
    """Listar todas as sessões do WhatsApp"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/sessions",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool  
def get_session_info(session: str = settings.default_session) -> Dict[str, Any]:
    """Obter informações de uma sessão específica"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/sessions/{session}",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def start_session(session: str = settings.default_session) -> Dict[str, Any]:
    """Iniciar uma sessão do WhatsApp"""
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sessions/{session}/start",
            headers=get_headers()
        )
        response.raise_for_status()
        return {"message": f"Sessão {session} iniciada com sucesso"}


@mcp.tool
def stop_session(session: str = settings.default_session) -> Dict[str, Any]:
    """Parar uma sessão do WhatsApp"""
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sessions/{session}/stop",
            headers=get_headers()
        )
        response.raise_for_status()
        return {"message": f"Sessão {session} parada com sucesso"}


@mcp.tool
def get_qr_code(session: str = settings.default_session) -> Dict[str, Any]:
    """Obter código QR para autenticação"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/auth/qr",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_my_profile(session: str = settings.default_session) -> Dict[str, Any]:
    """Obter informações do meu perfil"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/profile",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


# ==========================================
# FERRAMENTAS DE MENSAGENS
# ==========================================

@mcp.tool
def send_text_message(
    chat_id: str,
    text: str, 
    session: str = settings.default_session,
    reply_to: Optional[str] = None
) -> Dict[str, Any]:
    """Enviar mensagem de texto para um chat"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "text": text,
        "session": session
    }
    
    if reply_to:
        payload["reply_to"] = reply_to
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sendText",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def send_image_from_url(
    chat_id: str,
    image_url: str,
    caption: Optional[str] = None,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Enviar imagem de uma URL para um chat"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "file": {
            "mimetype": "image/jpeg",
            "url": image_url
        },
        "session": session
    }
    
    if caption:
        payload["caption"] = caption
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sendImage",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def send_image_base64(
    chat_id: str,
    base64_data: str,
    filename: str = "image.jpg",
    caption: Optional[str] = None,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Enviar imagem em base64 para um chat"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "file": {
            "mimetype": "image/jpeg",
            "filename": filename,
            "data": base64_data
        },
        "session": session
    }
    
    if caption:
        payload["caption"] = caption
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sendImage",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def send_file_from_url(
    chat_id: str,
    file_url: str,
    filename: str,
    mimetype: str = "application/octet-stream",
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Enviar arquivo de uma URL para um chat"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "file": {
            "mimetype": mimetype,
            "filename": filename,
            "url": file_url
        },
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sendFile",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def check_number_status(
    phone_number: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Verificar se um número está registrado no WhatsApp"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/checkNumberStatus",
            headers=get_headers(),
            params={"phone": phone_number, "session": session}
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def mark_as_read(
    chat_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Marcar mensagens de um chat como lidas"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/sendSeen",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return {"message": f"Mensagens marcadas como lidas para {chat_id}"}


@mcp.tool
def start_typing(
    chat_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Iniciar indicador de digitação"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/startTyping",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return {"message": f"Digitação iniciada para {chat_id}"}


@mcp.tool
def stop_typing(
    chat_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Parar indicador de digitação"""
    formatted_chat_id = format_chat_id(chat_id)
    
    payload = {
        "chatId": formatted_chat_id,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/stopTyping",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return {"message": f"Digitação parada para {chat_id}"}


# ==========================================
# FERRAMENTAS DE CHATS
# ==========================================

@mcp.tool
def get_chats(session: str = settings.default_session) -> List[Dict[str, Any]]:
    """Obter lista de todos os chats"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/chats",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_chat_messages(
    chat_id: str,
    limit: int = 20,
    session: str = settings.default_session
) -> List[Dict[str, Any]]:
    """Obter mensagens de um chat específico"""
    formatted_chat_id = format_chat_id(chat_id)
    
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/chats/{formatted_chat_id}/messages",
            headers=get_headers(),
            params={"limit": limit}
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def archive_chat(
    chat_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Arquivar um chat"""
    formatted_chat_id = format_chat_id(chat_id)
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/{session}/chats/{formatted_chat_id}/archive",
            headers=get_headers()
        )
        response.raise_for_status()
        return {"message": f"Chat {chat_id} arquivado com sucesso"}


@mcp.tool
def unarchive_chat(
    chat_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Desarquivar um chat"""
    formatted_chat_id = format_chat_id(chat_id)
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/{session}/chats/{formatted_chat_id}/unarchive",
            headers=get_headers()
        )
        response.raise_for_status()
        return {"message": f"Chat {chat_id} desarquivado com sucesso"}


# ==========================================
# FERRAMENTAS DE CONTATOS
# ==========================================

@mcp.tool
def get_all_contacts(session: str = settings.default_session) -> List[Dict[str, Any]]:
    """Obter todos os contatos"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/contacts/all",
            headers=get_headers(),
            params={"session": session}
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_contact_info(
    contact_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Obter informações de um contato"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/contacts",
            headers=get_headers(),
            params={"contactId": contact_id, "session": session}
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_contact_profile_picture(
    contact_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Obter foto de perfil de um contato"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/contacts/profile-picture",
            headers=get_headers(),
            params={"contactId": contact_id, "session": session}
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def block_contact(
    contact_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Bloquear um contato"""
    payload = {
        "contactId": contact_id,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/contacts/block",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return {"message": f"Contato {contact_id} bloqueado com sucesso"}


@mcp.tool
def unblock_contact(
    contact_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Desbloquear um contato"""
    payload = {
        "contactId": contact_id,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/contacts/unblock",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return {"message": f"Contato {contact_id} desbloqueado com sucesso"}


# ==========================================
# FERRAMENTAS DE GRUPOS
# ==========================================

@mcp.tool
def create_group(
    name: str,
    participants: List[str],
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Criar um novo grupo"""
    formatted_participants = [format_chat_id(p) for p in participants]
    
    payload = {
        "name": name,
        "participants": formatted_participants,
        "session": session
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/{session}/groups",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_groups(session: str = settings.default_session) -> List[Dict[str, Any]]:
    """Obter lista de grupos"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/groups",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_group_info(
    group_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Obter informações de um grupo"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/groups/{group_id}",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def add_group_participants(
    group_id: str,
    participants: List[str],
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Adicionar participantes a um grupo"""
    formatted_participants = [format_chat_id(p) for p in participants]
    
    payload = {
        "participants": formatted_participants
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/{session}/groups/{group_id}/participants/add",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def remove_group_participants(
    group_id: str,
    participants: List[str],
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Remover participantes de um grupo"""
    formatted_participants = [format_chat_id(p) for p in participants]
    
    payload = {
        "participants": formatted_participants
    }
    
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/{session}/groups/{group_id}/participants/remove",
            headers=get_headers(),
            json=payload
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_group_invite_code(
    group_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Obter código de convite do grupo"""
    with httpx.Client() as client:
        response = client.get(
            f"{settings.base_url}/api/{session}/groups/{group_id}/invite-code",
            headers=get_headers()
        )
        response.raise_for_status()
        return response.json()


@mcp.tool
def leave_group(
    group_id: str,
    session: str = settings.default_session
) -> Dict[str, Any]:
    """Sair de um grupo"""
    with httpx.Client() as client:
        response = client.post(
            f"{settings.base_url}/api/{session}/groups/{group_id}/leave",
            headers=get_headers()
        )
        response.raise_for_status()
        return {"message": f"Saiu do grupo {group_id} com sucesso"}


# ==========================================
# FERRAMENTAS DE STATUS/OBSERVABILIDADE
# ==========================================

@mcp.tool
def ping_server() -> Dict[str, Any]:
    """Fazer ping no servidor WAHA"""
    with httpx.Client() as client:
        response = client.get(f"{settings.base_url}/ping")
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_server_version() -> Dict[str, Any]:
    """Obter versão do servidor WAHA"""
    with httpx.Client() as client:
        response = client.get(f"{settings.base_url}/api/version")
        response.raise_for_status()
        return response.json()


@mcp.tool
def get_server_status() -> Dict[str, Any]:
    """Obter status do servidor WAHA"""
    with httpx.Client() as client:
        response = client.get(f"{settings.base_url}/api/server/status")
        response.raise_for_status()
        return response.json()


# ==========================================
# HEALTH CHECK ENDPOINT
# ==========================================

@mcp.tool
def health_check() -> Dict[str, Any]:
    """Verificar saúde do servidor MCP e conexão com WAHA"""
    try:
        # Testar conexão com WAHA
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{settings.base_url}/ping")
            waha_status = "healthy" if response.status_code == 200 else "unhealthy"
    except Exception:
        waha_status = "unreachable"
    
    return {
        "status": "healthy",
        "timestamp": "2025-06-14T00:00:00Z",
        "version": "1.0.0",
        "waha_connection": waha_status,
        "base_url": settings.base_url,
        "default_session": settings.default_session
    }


if __name__ == "__main__":
    # Executar o servidor
    mcp.run()
