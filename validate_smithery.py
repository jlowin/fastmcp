#!/usr/bin/env python3
"""
Validador de Configuração Smithery
----------------------------------
Script para validar se os arquivos de configuração estão corretos.
"""

import os
import yaml
import json
from pathlib import Path

def validate_smithery_config():
    """Validar arquivo smithery.yaml"""
    smithery_file = Path("smithery.yaml")
    
    if not smithery_file.exists():
        print("❌ Arquivo smithery.yaml não encontrado")
        return False
    
    try:
        with open(smithery_file) as f:
            config = yaml.safe_load(f)
        
        # Validar campos obrigatórios
        required_fields = ["apiVersion", "kind", "metadata", "spec"]
        for field in required_fields:
            if field not in config:
                print(f"❌ Campo obrigatório '{field}' não encontrado em smithery.yaml")
                return False
        
        # Validar metadata
        metadata = config["metadata"]
        if "name" not in metadata:
            print("❌ Campo 'metadata.name' obrigatório")
            return False
            
        # Validar spec
        spec = config["spec"]
        if "build" not in spec:
            print("❌ Campo 'spec.build' obrigatório")
            return False
            
        print("✅ smithery.yaml válido")
        return True
        
    except yaml.YAMLError as e:
        print(f"❌ Erro no formato YAML: {e}")
        return False
    except Exception as e:
        print(f"❌ Erro ao validar smithery.yaml: {e}")
        return False

def validate_dockerfile():
    """Validar Dockerfile"""
    dockerfile = Path("Dockerfile")
    
    if not dockerfile.exists():
        print("❌ Dockerfile não encontrado")
        return False
    
    try:
        with open(dockerfile) as f:
            content = f.read()
        
        # Verificar comandos essenciais
        required_commands = ["FROM", "WORKDIR", "COPY", "CMD"]
        for cmd in required_commands:
            if cmd not in content:
                print(f"❌ Comando '{cmd}' não encontrado no Dockerfile")
                return False
        
        print("✅ Dockerfile válido")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao validar Dockerfile: {e}")
        return False

def validate_server_entrypoint():
    """Validar script server.py"""
    server_file = Path("server.py")
    
    if not server_file.exists():
        print("❌ Arquivo server.py não encontrado")
        return False
    
    try:
        with open(server_file) as f:
            content = f.read()
        
        # Verificar imports essenciais
        required_imports = ["import os", "import sys", "from pathlib import Path"]
        for imp in required_imports:
            if imp not in content:
                print(f"❌ Import '{imp}' não encontrado em server.py")
                return False
        
        print("✅ server.py válido")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao validar server.py: {e}")
        return False

def validate_mcp_server():
    """Validar servidor MCP principal"""
    waha_file = Path("examples/waha_whatsapp.py")
    
    if not waha_file.exists():
        print("❌ Arquivo examples/waha_whatsapp.py não encontrado")
        return False
    
    try:
        with open(waha_file) as f:
            content = f.read()
        
        # Verificar elementos essenciais do MCP
        required_elements = [
            "from fastmcp import FastMCP",
            "@mcp.tool",
            "mcp = FastMCP",
            "def send_text_message"
        ]
        
        for element in required_elements:
            if element not in content:
                print(f"❌ Elemento '{element}' não encontrado no servidor MCP")
                return False
        
        print("✅ Servidor MCP válido")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao validar servidor MCP: {e}")
        return False

def main():
    """Função principal de validação"""
    print("🔍 Validando configuração para Smithery...")
    print("=" * 50)
    
    validations = [
        validate_smithery_config,
        validate_dockerfile,
        validate_server_entrypoint,
        validate_mcp_server
    ]
    
    all_valid = True
    for validation in validations:
        if not validation():
            all_valid = False
    
    print("=" * 50)
    if all_valid:
        print("🎉 Todas as validações passaram!")
        print("✅ Projeto pronto para deploy no Smithery")
        print()
        print("Próximos passos:")
        print("1. git add .")
        print("2. git commit -m 'Add Smithery configuration'")
        print("3. git push")
        print("4. Deploy no Smithery")
    else:
        print("❌ Algumas validações falharam")
        print("❗ Corrija os erros antes de fazer deploy")
    
    return all_valid

if __name__ == "__main__":
    main()
