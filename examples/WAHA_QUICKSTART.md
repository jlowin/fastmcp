# WAHA MCP Server - Guia Rápido

## 🚀 Instalação Rápida

### 1. Instalar dependências
```bash
pip install -r requirements-waha.txt
```

### 2. Configurar WAHA
Baixe e execute o servidor WAHA:
```bash
# Usando Docker
docker run -it --rm -p 3000:3000/tcp devlikeapro/waha

# Ou baixe o binário do GitHub releases
```

### 3. Testar conexão
```bash
python demo_waha.py test
```

## 📱 Uso Básico

### Versão Simples (Recomendada para iniciantes)
```bash
python waha_simple.py
```

Ferramentas disponíveis:
- `send_message(phone_number, message)` - Enviar mensagem
- `get_session_status()` - Ver status da sessão
- `start_whatsapp_session()` - Iniciar sessão
- `get_qr_code_for_whatsapp()` - Obter QR code
- `check_phone_number(phone_number)` - Verificar número
- `get_my_chats()` - Listar chats

### Versão Completa (Todas as funcionalidades)
```bash
python waha_whatsapp.py
```

## 🔧 Configuração

### Arquivo .env (opcional)
```env
WAHA_BASE_URL=http://localhost:3000
WAHA_API_KEY=sua_api_key_aqui
WAHA_DEFAULT_SESSION=default
```

### Configuração no código
Edite diretamente as variáveis no início do arquivo:
```python
BASE_URL = "http://localhost:3000"
DEFAULT_SESSION = "default"
```

## 🎯 Fluxo de Trabalho

1. **Iniciar WAHA**: Execute o servidor WAHA
2. **Iniciar MCP**: Execute `python waha_simple.py`
3. **Verificar status**: Use `get_session_status()`
4. **Iniciar sessão**: Use `start_whatsapp_session()`
5. **Obter QR**: Use `get_qr_code_for_whatsapp()`
6. **Escanear QR**: Use WhatsApp para escanear
7. **Enviar mensagens**: Use `send_message()`

## 📞 Formatos de Número

- **Brasil**: `5511999999999` (sem +)
- **Outros países**: `1234567890` (código do país + número)
- **Grupos**: Use o ID completo com `@g.us`

## 🛠️ Troubleshooting

### Erro de conexão
- Verifique se WAHA está rodando: `curl http://localhost:3000/ping`
- Verifique a URL no código/configuração

### QR Code não aparece
- A sessão pode já estar autenticada
- Tente parar e reiniciar a sessão

### Mensagem não enviada
- Verifique se o número está correto
- Confirme que a sessão está `WORKING`
- Teste com `check_phone_number()` primeiro

## 📚 Exemplos

### Enviar mensagem simples
```python
send_message("5511999999999", "Olá do MCP!")
```

### Verificar número antes de enviar
```python
status = check_phone_number("5511999999999")
if "Registrado" in status:
    send_message("5511999999999", "Número verificado!")
```

### Obter QR code para nova sessão
```python
start_whatsapp_session("nova_sessao")
qr = get_qr_code_for_whatsapp("nova_sessao")
print(qr)
```

## 🔗 Links Úteis

- [WAHA Documentation](https://waha.devlike.pro/)
- [WAHA GitHub](https://github.com/devlikeapro/waha)
- [FastMCP Documentation](https://fastmcp.com/)

## ⚠️ Notas Importantes

- Use números reais apenas para testes
- Respeite os termos de uso do WhatsApp
- O QR code expira após alguns minutos
- Sessões podem desconectar automaticamente
