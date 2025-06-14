#!/usr/bin/env python3
"""
WAHA MCP Server Entrypoint
--------------------------
Ponto de entrada para o servidor MCP do WAHA otimizado para deploy.
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# Adicionar src ao path
src_path = Path(__file__).parent / "src"
sys.path.insert(0, str(src_path))

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("waha-mcp")

def main():
    """Função principal do servidor"""
    try:
        # Importar e executar o servidor WAHA
        from examples.waha_whatsapp import mcp
        
        logger.info("🚀 Iniciando WAHA MCP Server...")
        logger.info(f"📡 WAHA Base URL: {os.getenv('WAHA_BASE_URL', 'http://localhost:3000')}")
        logger.info(f"📱 Sessão padrão: {os.getenv('WAHA_DEFAULT_SESSION', 'default')}")
        
        # Executar servidor
        mcp.run()
        
    except ImportError as e:
        logger.error(f"❌ Erro ao importar módulos: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"❌ Erro inesperado: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
