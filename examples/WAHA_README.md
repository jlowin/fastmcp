# WAHA WhatsApp MCP Server

Este servidor MCP fornece integração completa com WAHA (WhatsApp HTTP API), permitindo:

## Funcionalidades Implementadas

### 🖥️ Gerenciamento de Sessões
- `list_sessions()` - Listar todas as sessões
- `get_session_info(session)` - Obter informações de uma sessão
- `start_session(session)` - Iniciar sessão
- `stop_session(session)` - Parar sessão
- `get_qr_code(session)` - Obter QR code para autenticação
- `get_my_profile(session)` - Obter perfil da conta autenticada

### 📤 Envio de Mensagens
- `send_text_message(chat_id, text, session, reply_to)` - Enviar mensagem de texto
- `send_image_from_url(chat_id, image_url, caption, session)` - Enviar imagem de URL
- `send_image_base64(chat_id, base64_data, filename, caption, session)` - Enviar imagem em base64
- `send_file_from_url(chat_id, file_url, filename, mimetype, session)` - Enviar arquivo de URL
- `mark_as_read(chat_id, session)` - Marcar mensagens como lidas
- `start_typing(chat_id, session)` - Iniciar indicador de digitação
- `stop_typing(chat_id, session)` - Parar indicador de digitação

### 💬 Gerenciamento de Chats
- `get_chats(session)` - Obter lista de chats
- `get_chat_messages(chat_id, limit, session)` - Obter mensagens de um chat
- `archive_chat(chat_id, session)` - Arquivar chat
- `unarchive_chat(chat_id, session)` - Desarquivar chat

### 👤 Gerenciamento de Contatos
- `get_all_contacts(session)` - Obter todos os contatos
- `get_contact_info(contact_id, session)` - Obter informações de contato
- `get_contact_profile_picture(contact_id, session)` - Obter foto de perfil
- `block_contact(contact_id, session)` - Bloquear contato
- `unblock_contact(contact_id, session)` - Desbloquear contato
- `check_number_status(phone_number, session)` - Verificar se número está no WhatsApp

### 👥 Gerenciamento de Grupos
- `create_group(name, participants, session)` - Criar grupo
- `get_groups(session)` - Obter lista de grupos
- `get_group_info(group_id, session)` - Obter informações do grupo
- `add_group_participants(group_id, participants, session)` - Adicionar participantes
- `remove_group_participants(group_id, participants, session)` - Remover participantes
- `get_group_invite_code(group_id, session)` - Obter código de convite
- `leave_group(group_id, session)` - Sair do grupo

### 🔍 Monitoramento
- `ping_server()` - Ping no servidor
- `get_server_version()` - Versão do servidor
- `get_server_status()` - Status do servidor

## Configuração

1. Copie o arquivo `.env.waha.example` para `.env`:
   ```bash
   cp .env.waha.example .env
   ```

2. Configure as variáveis no arquivo `.env`:
   ```env
   WAHA_BASE_URL=http://localhost:3000
   WAHA_API_KEY=your_api_key_here  # opcional
   WAHA_DEFAULT_SESSION=default
   ```

## Execução

### Como script standalone:
```bash
python waha_whatsapp.py
```

### Como servidor MCP:
```bash
fastmcp run waha_whatsapp.py
```

## Uso

### Exemplos de Chat IDs
- **Número individual**: `5511999999999@c.us` ou apenas `5511999999999`
- **Grupo**: `123456789-987654321@g.us`

### Formatação Automática
O servidor automaticamente formata os IDs dos chats:
- Números sem `@c.us` são convertidos automaticamente
- Grupos devem incluir `@g.us`

### Fluxo Típico de Uso

1. **Iniciar sessão**:
   ```python
   start_session("minha_sessao")
   ```

2. **Obter QR code** (se necessário):
   ```python
   get_qr_code("minha_sessao")
   ```

3. **Verificar status**:
   ```python
   get_session_info("minha_sessao")
   ```

4. **Enviar mensagem**:
   ```python
   send_text_message("5511999999999", "Olá!", "minha_sessao")
   ```

## Dependências

- `fastmcp` - Framework MCP
- `httpx` - Cliente HTTP
- `pydantic` - Validação de dados
- `pydantic-settings` - Configurações

## Notas Importantes

- O servidor WAHA deve estar executando e acessível
- Algumas funcionalidades podem requerer autenticação (API key)
- O QR code deve ser escaneado para autenticar a sessão
- IDs de chat seguem o formato padrão do WhatsApp Web
