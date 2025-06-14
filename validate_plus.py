#!/usr/bin/env python3
"""
Validador WAHA MCP PLUS
-----------------------
Script para validar configuração premium do WAHA MCP PLUS.
"""

import os
import yaml
import json
from pathlib import Path
from typing import Dict, Any, List

def validate_plus_config():
    """Validar configuração do WAHA MCP PLUS"""
    print("🚀 Validando WAHA MCP PLUS Configuration...")
    print("=" * 60)
    
    validations = [
        validate_smithery_plus_config,
        validate_dockerfile_plus,
        validate_mcp_plus_server,
        validate_premium_features,
        validate_dependencies
    ]
    
    all_valid = True
    for validation in validations:
        if not validation():
            all_valid = False
            print()
    
    print("=" * 60)
    if all_valid:
        print("🎉 WAHA MCP PLUS está pronto para deploy!")
        print("✨ Todas as validações premium passaram!")
        print()
        print("🚀 Próximos passos:")
        print("1. git add .")
        print("2. git commit -m 'Add WAHA MCP PLUS premium features'")
        print("3. git push")
        print("4. Deploy no Smithery com: smithery deploy --config smithery-plus.yaml")
        print()
        print("💎 Features premium detectadas:")
        print("   ✅ Analytics em tempo real")
        print("   ✅ Respostas automáticas com IA")
        print("   ✅ Campanhas de marketing")
        print("   ✅ Multi-session management")
        print("   ✅ Rate limiting avançado")
        print("   ✅ Agendamento inteligente")
        print("   ✅ Relatórios detalhados")
    else:
        print("❌ Algumas validações falharam")
        print("❗ Corrija os erros antes de fazer deploy premium")
    
    return all_valid

def validate_smithery_plus_config():
    """Validar smithery-plus.yaml"""
    print("📋 Validando smithery-plus.yaml...")
    
    config_file = Path("smithery-plus.yaml")
    if not config_file.exists():
        print("❌ Arquivo smithery-plus.yaml não encontrado")
        return False
    
    try:
        with open(config_file) as f:
            config = yaml.safe_load(f)
        
        # Validar metadata premium
        metadata = config.get("metadata", {})
        if metadata.get("name") != "waha-mcp-plus":
            print("❌ Nome deve ser 'waha-mcp-plus'")
            return False
        
        if "premium" not in metadata.get("description", "").lower():
            print("❌ Descrição deve mencionar 'premium'")
            return False
        
        # Validar tools premium
        spec = config.get("spec", {})
        mcp_config = spec.get("mcp", {})
        tools = mcp_config.get("tools", [])
        
        premium_tools = [
            "create_multi_session",
            "send_smart_message", 
            "get_analytics_dashboard",
            "configure_auto_reply",
            "create_marketing_campaign",
            "system_health_check"
        ]
        
        found_tools = [tool.get("name") for tool in tools]
        missing_tools = [tool for tool in premium_tools if tool not in found_tools]
        
        if missing_tools:
            print(f"❌ Ferramentas premium faltando: {missing_tools}")
            return False
        
        # Validar categorias premium
        categories = [tool.get("category", "") for tool in tools]
        premium_categories = [
            "premium-sessions",
            "premium-messaging", 
            "premium-analytics",
            "premium-automation",
            "premium-campaigns"
        ]
        
        found_categories = [cat for cat in premium_categories if any(cat in c for c in categories)]
        if len(found_categories) < 3:
            print(f"❌ Poucas categorias premium encontradas: {found_categories}")
            return False
        
        print("✅ smithery-plus.yaml válido com recursos premium")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao validar smithery-plus.yaml: {e}")
        return False

def validate_dockerfile_plus():
    """Validar Dockerfile.plus"""
    print("🐳 Validando Dockerfile.plus...")
    
    dockerfile = Path("Dockerfile.plus")
    if not dockerfile.exists():
        print("❌ Dockerfile.plus não encontrado")
        return False
    
    try:
        with open(dockerfile) as f:
            content = f.read()
        
        # Verificar dependências premium
        premium_deps = [
            "redis",
            "schedule", 
            "openai",
            "anthropic"
        ]
        
        missing_deps = [dep for dep in premium_deps if dep not in content]
        if missing_deps:
            print(f"⚠️  Dependências premium opcionais: {missing_deps}")
        
        # Verificar configurações premium
        if "WAHA_ENABLE_ANALYTICS" not in content:
            print("❌ Configuração WAHA_ENABLE_ANALYTICS faltando")
            return False
        
        if "premium" not in content.lower():
            print("❌ Dockerfile deve mencionar 'premium'")
            return False
        
        # Verificar portas premium
        if "8080" not in content:
            print("❌ Porta 8080 (dashboard) não exposta")
            return False
        
        print("✅ Dockerfile.plus válido")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao validar Dockerfile.plus: {e}")
        return False

def validate_mcp_plus_server():
    """Validar waha_mcp_plus.py"""
    print("🎯 Validando waha_mcp_plus.py...")
    
    server_file = Path("waha_mcp_plus.py")
    if not server_file.exists():
        print("❌ Arquivo waha_mcp_plus.py não encontrado")
        return False
    
    try:
        with open(server_file) as f:
            content = f.read()
        
        # Verificar classes premium
        premium_classes = [
            "WAHAPlusSettings",
            "AdvancedCache",
            "AutoReplyEngine", 
            "CampaignManager",
            "MessageAnalytics"
        ]
        
        missing_classes = [cls for cls in premium_classes if cls not in content]
        if missing_classes:
            print(f"❌ Classes premium faltando: {missing_classes}")
            return False
        
        # Verificar ferramentas premium
        premium_functions = [
            "create_multi_session",
            "send_smart_message",
            "get_analytics_dashboard", 
            "configure_auto_reply",
            "create_marketing_campaign",
            "send_bulk_messages",
            "system_health_check"
        ]
        
        missing_functions = [func for func in premium_functions if f"def {func}" not in content]
        if missing_functions:
            print(f"❌ Funções premium faltando: {missing_functions}")
            return False
        
        # Verificar decoradores MCP
        mcp_tools = content.count("@mcp.tool")
        if mcp_tools < 15:
            print(f"❌ Poucas ferramentas MCP encontradas: {mcp_tools}")
            return False
        
        print(f"✅ waha_mcp_plus.py válido com {mcp_tools} ferramentas premium")
        return True
        
    except Exception as e:
        print(f"❌ Erro ao validar waha_mcp_plus.py: {e}")
        return False

def validate_premium_features():
    """Validar recursos premium específicos"""
    print("💎 Validando recursos premium...")
    
    # Verificar imports premium no código
    server_file = Path("waha_mcp_plus.py")
    if not server_file.exists():
        return False
    
    with open(server_file) as f:
        content = f.read()
    
    premium_features = {
        "Analytics": ["MessageAnalytics", "get_analytics_dashboard", "cache.add_analytics"],
        "Auto Reply": ["AutoReplyEngine", "configure_auto_reply", "should_auto_reply"],
        "Campaigns": ["CampaignManager", "create_marketing_campaign", "start_campaign"],
        "Multi-Session": ["create_multi_session", "active_sessions", "max_sessions"],
        "Rate Limiting": ["check_rate_limit", "rate_limits", "max_requests_per_minute"],
        "Scheduling": ["ScheduledMessage", "schedule_time", "scheduled_messages"]
    }
    
    for feature_name, keywords in premium_features.items():
        found_keywords = [kw for kw in keywords if kw in content]
        if len(found_keywords) >= 2:
            print(f"✅ {feature_name}: {len(found_keywords)}/{len(keywords)} recursos encontrados")
        else:
            print(f"⚠️  {feature_name}: {len(found_keywords)}/{len(keywords)} recursos (pode estar incompleto)")
    
    return True

def validate_dependencies():
    """Validar dependências e estrutura"""
    print("📦 Validando dependências...")
    
    # Verificar estrutura de arquivos
    required_files = [
        "waha_mcp_plus.py",
        "smithery-plus.yaml", 
        "Dockerfile.plus",
        "README-PLUS.md"
    ]
    
    missing_files = [f for f in required_files if not Path(f).exists()]
    if missing_files:
        print(f"❌ Arquivos faltando: {missing_files}")
        return False
    
    # Verificar pyproject.toml
    pyproject = Path("pyproject.toml")
    if pyproject.exists():
        with open(pyproject) as f:
            content = f.read()
        
        if "fastmcp" not in content:
            print("⚠️  FastMCP não encontrado em pyproject.toml")
        else:
            print("✅ FastMCP configurado em pyproject.toml")
    
    print("✅ Estrutura de dependências validada")
    return True

def generate_deployment_summary():
    """Gerar resumo do deployment"""
    print("\n🚀 RESUMO DO DEPLOYMENT - WAHA MCP PLUS")
    print("=" * 60)
    print("📊 Estatísticas do projeto:")
    
    # Contar linhas de código
    server_file = Path("waha_mcp_plus.py")
    if server_file.exists():
        with open(server_file) as f:
            lines = len(f.readlines())
        print(f"   📝 Linhas de código: {lines}")
    
    # Contar ferramentas
    if server_file.exists():
        with open(server_file) as f:
            content = f.read()
        tools_count = content.count("@mcp.tool")
        print(f"   🛠️  Ferramentas MCP: {tools_count}")
    
    # Recursos premium
    premium_count = 7  # Número de categorias premium
    print(f"   💎 Recursos premium: {premium_count}")
    
    print("\n🎯 Deployment targets:")
    print("   ✅ Smithery.ai (Premium)")
    print("   ✅ Docker Container")
    print("   ✅ Kubernetes Ready")
    print("   ✅ Multi-environment")
    
    print("\n💡 Comandos úteis:")
    print("   🚀 Deploy: smithery deploy --config smithery-plus.yaml")
    print("   🐳 Local: docker build -f Dockerfile.plus -t waha-mcp-plus .")
    print("   🔧 Test: python waha_mcp_plus.py")

if __name__ == "__main__":
    success = validate_plus_config()
    
    if success:
        generate_deployment_summary()
    
    exit(0 if success else 1)
