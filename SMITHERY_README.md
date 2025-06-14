# WAHA WhatsApp MCP Server para Smithery

Este é um servidor MCP completo para integração com WhatsApp através da API WAHA, pronto para deploy no [Smithery](https://smithery.ai).

## 🚀 Deploy Rápido

### 1. No Smithery
```bash
# Clone este repositório
git clone <seu-repo>
cd fastmcp

# Deploy no Smithery
smithery deploy
```

### 2. Configuração
Configure as variáveis de ambiente no painel do Smithery:
- `WAHA_BASE_URL`: URL do seu servidor WAHA
- `WAHA_DEFAULT_SESSION`: Nome da sessão padrão

### 3. Dependências
O servidor WAHA deve estar rodando separadamente. Você pode usar:
```bash
docker run -d -p 3000:3000 devlikeapro/waha
```

## 🛠️ Funcionalidades

### ✅ Ferramentas Disponíveis (40+)
- **Sessões**: start_session, get_session_info, get_qr_code
- **Mensagens**: send_text_message, send_image_from_url
- **Chats**: get_chats, get_chat_messages, archive_chat
- **Contatos**: get_all_contacts, check_number_status
- **Grupos**: create_group, add_group_participants
- **Monitoramento**: ping_server, get_server_status

## 📋 Arquivos de Configuração

### `smithery.yaml`
Configuração completa do MCP server para Smithery:
- Definições de ferramentas
- Configuração de runtime
- Dependências externas
- Health checks

### `Dockerfile`
Container otimizado para produção:
- Base Python 3.11-slim
- Dependências via UV
- Configuração de ambiente
- Entrypoint otimizado

### `server.py`
Entrypoint principal do servidor com:
- Logging configurado
- Tratamento de erros
- Configuração de paths
- Importação otimizada

## 🔧 Configuração Local

Para testar localmente antes do deploy:

```bash
# 1. Instalar dependências
uv sync

# 2. Executar WAHA
docker run -d -p 3000:3000 devlikeapro/waha

# 3. Executar MCP server
python server.py

# 4. Testar
python examples/demo_waha.py test
```

## 📚 Uso no Smithery

Após o deploy, você pode usar o servidor em qualquer aplicação MCP:

```python
import mcp

# Conectar ao servidor
client = mcp.connect("waha-whatsapp-mcp")

# Enviar mensagem
await client.call_tool("send_text_message", {
    "chat_id": "5511999999999",
    "text": "Olá do Smithery!"
})

# Verificar número
status = await client.call_tool("check_number_status", {
    "phone_number": "5511999999999"
})
```

## 🔍 Monitoramento

O servidor inclui health checks automáticos:
- **Readiness**: `/health` (porta 8000)
- **Liveness**: `/health` (porta 8000)

## 🐛 Troubleshooting

### Erro de conexão com WAHA
- Verifique se `WAHA_BASE_URL` está correto
- Confirme que WAHA está rodando e acessível

### Sessão não inicia
- Use `get_qr_code` para obter QR code
- Escaneie com WhatsApp
- Verifique `get_session_info` para status

### Ferramentas não respondem
- Verifique logs do container
- Confirme que sessão está `WORKING`
- Teste conectividade com `ping_server`

## 📖 Links Úteis

- [Documentação WAHA](https://waha.devlike.pro)
- [Smithery Docs](https://smithery.ai/docs)
- [MCP Specification](https://modelcontextprotocol.io)

## 🤝 Suporte

Para suporte e questões:
1. Verifique os logs no painel Smithery
2. Teste localmente primeiro
3. Consulte a documentação WAHA
4. Abra uma issue no repositório
