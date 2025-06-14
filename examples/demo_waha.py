#!/usr/bin/env python3
"""
Demo do WAHA MCP Server
-----------------------
Script de demonstração para testar o servidor MCP do WAHA.
"""

import asyncio
import httpx
from fastmcp.client import create_client


async def demo_waha_mcp():
    """Demonstração das funcionalidades do WAHA MCP"""
    
    print("🚀 Iniciando demonstração do WAHA MCP Server")
    print("=" * 50)
    
    # Conectar ao servidor MCP
    client = await create_client("stdio://python waha_simple.py")
    
    try:
        # 1. Verificar status da sessão
        print("📱 Verificando status da sessão...")
        result = await client.call_tool("get_session_status")
        print(f"Status: {result}")
        print()
        
        # 2. Verificar se servidor está rodando
        try:
            async with httpx.AsyncClient() as http_client:
                response = await http_client.get("http://localhost:3000/ping")
                if response.status_code == 200:
                    print("✅ Servidor WAHA está rodando")
                else:
                    print("❌ Servidor WAHA não está respondendo")
        except Exception as e:
            print(f"❌ Erro ao conectar com servidor WAHA: {e}")
            print("💡 Certifique-se de que o servidor WAHA está rodando em http://localhost:3000")
            return
        
        print()
        
        # 3. Verificar número (exemplo)
        print("🔍 Verificando número de exemplo...")
        result = await client.call_tool("check_phone_number", {"phone_number": "5511999999999"})
        print(f"Resultado: {result}")
        print()
        
        # 4. Obter chats (se sessão estiver ativa)
        print("💬 Obtendo lista de chats...")
        result = await client.call_tool("get_my_chats")
        print(f"Chats: {result}")
        print()
        
        # 5. Exemplo de envio de mensagem (comentado para segurança)
        print("📤 Exemplo de envio de mensagem:")
        print("   Para enviar uma mensagem, use:")
        print("   await client.call_tool('send_message', {")
        print("       'phone_number': '5511999999999',")
        print("       'message': 'Olá do MCP!'})")
        print("   (Descomente no código para testar)")
        print()
        
        print("✅ Demonstração concluída!")
        
    except Exception as e:
        print(f"❌ Erro durante demonstração: {e}")
    
    finally:
        await client.close()


async def test_server_connection():
    """Testar conexão com servidor WAHA"""
    print("🔗 Testando conexão com servidor WAHA...")
    
    try:
        async with httpx.AsyncClient() as client:
            # Ping
            response = await client.get("http://localhost:3000/ping")
            if response.status_code == 200:
                print("✅ Ping: OK")
            
            # Versão
            response = await client.get("http://localhost:3000/api/version")
            if response.status_code == 200:
                version = response.json()
                print(f"✅ Versão: {version}")
            
            # Sessões
            response = await client.get("http://localhost:3000/api/sessions")
            if response.status_code == 200:
                sessions = response.json()
                print(f"✅ Sessões disponíveis: {len(sessions)}")
                for session in sessions:
                    name = session.get('name', 'N/A')
                    status = session.get('status', 'N/A')
                    print(f"   - {name}: {status}")
            
    except httpx.ConnectError:
        print("❌ Não foi possível conectar ao servidor WAHA")
        print("💡 Certifique-se de que o WAHA está rodando em http://localhost:3000")
    except Exception as e:
        print(f"❌ Erro: {e}")


if __name__ == "__main__":
    print("WAHA MCP Server - Demo")
    print("=" * 30)
    print()
    
    # Escolher o que executar
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        asyncio.run(test_server_connection())
    else:
        print("Executando demonstração completa...")
        print("Para testar apenas a conexão, use: python demo_waha.py test")
        print()
        asyncio.run(demo_waha_mcp())
