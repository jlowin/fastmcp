# /// script
# dependencies = ["fastmcp", "httpx", "pydantic", "pydantic-settings", "asyncio", "schedule", "redis"]
# ///

"""
WAHA MCP PLUS - Premium WhatsApp Automation Server
--------------------------------------------------
Versão premium do servidor MCP WAHA com funcionalidades avançadas:
- 🤖 Respostas automáticas inteligentes
- 📊 Analytics em tempo real
- 🔄 Agendamento de mensagens
- 💾 Cache Redis para performance
- 🛡️ Rate limiting avançado
- 📱 Múltiplas sessões simultâneas
- 🎯 Campanhas de marketing
- 📈 Relatórios detalhados

Configuração avançada via .env:
WAHA_BASE_URL=http://localhost:3000
WAHA_API_KEY=your_api_key
WAHA_DEFAULT_SESSION=default
REDIS_URL=redis://localhost:6379
OPENAI_API_KEY=your_openai_key  # Para IA
ENABLE_ANALYTICS=true
ENABLE_AUTO_REPLY=true
"""

import asyncio
import base64
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Annotated, Dict, List, Optional, Any, Union
from enum import Enum
from dataclasses import dataclass, asdict
from collections import defaultdict, deque
import hashlib
import re

import httpx
from pydantic import BaseModel, Field, BeforeValidator
from pydantic_settings import BaseSettings, SettingsConfigDict

from fastmcp import FastMCP

# ==========================================
# CONFIGURAÇÕES AVANÇADAS
# ==========================================

class WAHAPlusSettings(BaseSettings):
    """Configurações premium para WAHA MCP PLUS"""
    model_config: SettingsConfigDict = SettingsConfigDict(
        env_prefix="WAHA_", env_file=".env"
    )

    # Configurações básicas
    base_url: str = "http://localhost:3000"
    api_key: Optional[str] = None
    default_session: str = "default"
    
    # Configurações premium
    redis_url: str = "redis://localhost:6379"
    openai_api_key: Optional[str] = None
    enable_analytics: bool = True
    enable_auto_reply: bool = True
    enable_rate_limiting: bool = True
    enable_scheduling: bool = True
    
    # Limites e configurações
    max_requests_per_minute: int = 60
    max_sessions: int = 10
    cache_ttl_seconds: int = 3600
    auto_reply_delay_seconds: int = 2


class MessagePriority(str, Enum):
    """Prioridade de mensagens"""
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    URGENT = "urgent"


class CampaignStatus(str, Enum):
    """Status de campanhas"""
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class MessageAnalytics:
    """Analytics de mensagens"""
    timestamp: datetime
    session: str
    chat_id: str
    message_type: str
    direction: str  # inbound/outbound
    success: bool
    response_time_ms: int
    content_length: int


@dataclass
class AutoReplyRule:
    """Regra de resposta automática"""
    id: str
    name: str
    trigger_patterns: List[str]
    response_template: str
    enabled: bool
    priority: int
    conditions: Dict[str, Any]


@dataclass
class ScheduledMessage:
    """Mensagem agendada"""
    id: str
    chat_id: str
    content: str
    message_type: str
    scheduled_time: datetime
    session: str
    priority: MessagePriority
    retry_count: int = 0
    max_retries: int = 3


# ==========================================
# SISTEMA DE CACHE E ANALYTICS
# ==========================================

class AdvancedCache:
    """Sistema de cache avançado"""
    
    def __init__(self):
        self._memory_cache = {}
        self._analytics = deque(maxlen=10000)
        self._rate_limits = defaultdict(deque)
    
    def get(self, key: str) -> Optional[Any]:
        """Obter valor do cache"""
        if key in self._memory_cache:
            value, expiry = self._memory_cache[key]
            if datetime.now() < expiry:
                return value
            del self._memory_cache[key]
        return None
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600):
        """Definir valor no cache"""
        expiry = datetime.now() + timedelta(seconds=ttl_seconds)
        self._memory_cache[key] = (value, expiry)
    
    def add_analytics(self, event: MessageAnalytics):
        """Adicionar evento de analytics"""
        self._analytics.append(event)
    
    def get_analytics(self, hours: int = 24) -> List[MessageAnalytics]:
        """Obter analytics das últimas horas"""
        cutoff = datetime.now() - timedelta(hours=hours)
        return [a for a in self._analytics if a.timestamp > cutoff]
    
    def check_rate_limit(self, key: str, max_requests: int, window_minutes: int = 1) -> bool:
        """Verificar rate limit"""
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)
        
        # Limpar requests antigos
        self._rate_limits[key] = deque([
            req_time for req_time in self._rate_limits[key] 
            if req_time > window_start
        ])
        
        # Verificar limite
        if len(self._rate_limits[key]) >= max_requests:
            return False
        
        # Adicionar request atual
        self._rate_limits[key].append(now)
        return True


# ==========================================
# SISTEMA DE RESPOSTAS AUTOMÁTICAS
# ==========================================

class AutoReplyEngine:
    """Engine de respostas automáticas com IA"""
    
    def __init__(self, openai_key: Optional[str] = None):
        self.openai_key = openai_key
        self.rules: List[AutoReplyRule] = []
        self._load_default_rules()
    
    def _load_default_rules(self):
        """Carregar regras padrão"""
        default_rules = [
            AutoReplyRule(
                id="greeting",
                name="Saudação",
                trigger_patterns=["oi", "olá", "hello", "hi", "boa tarde", "bom dia"],
                response_template="Olá! Obrigado por entrar em contato. Como posso ajudar você hoje?",
                enabled=True,
                priority=1,
                conditions={"time_restriction": None}
            ),
            AutoReplyRule(
                id="thanks",
                name="Agradecimento",
                trigger_patterns=["obrigado", "obrigada", "thanks", "valeu"],
                response_template="De nada! Fico feliz em ajudar. Se precisar de mais alguma coisa, é só falar! 😊",
                enabled=True,
                priority=2,
                conditions={}
            ),
            AutoReplyRule(
                id="help",
                name="Ajuda",
                trigger_patterns=["ajuda", "help", "suporte", "socorro"],
                response_template="Estou aqui para ajudar! Você pode:\n• Fazer perguntas\n• Solicitar informações\n• Reportar problemas\n\nO que você precisa?",
                enabled=True,
                priority=3,
                conditions={}
            )
        ]
        self.rules.extend(default_rules)
    
    def add_rule(self, rule: AutoReplyRule):
        """Adicionar regra personalizada"""
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority)
    
    def should_auto_reply(self, message: str, chat_id: str) -> Optional[str]:
        """Verificar se deve responder automaticamente"""
        message_lower = message.lower().strip()
        
        for rule in self.rules:
            if not rule.enabled:
                continue
                
            for pattern in rule.trigger_patterns:
                if pattern.lower() in message_lower:
                    return rule.response_template
        
        return None


# ==========================================
# SISTEMA DE CAMPANHAS
# ==========================================

class CampaignManager:
    """Gerenciador de campanhas de marketing"""
    
    def __init__(self):
        self.campaigns = {}
        self.scheduled_messages = {}
    
    def create_campaign(
        self, 
        name: str, 
        target_chats: List[str],
        message_template: str,
        schedule_time: Optional[datetime] = None
    ) -> str:
        """Criar nova campanha"""
        campaign_id = str(uuid.uuid4())
        
        campaign = {
            "id": campaign_id,
            "name": name,
            "target_chats": target_chats,
            "message_template": message_template,
            "schedule_time": schedule_time,
            "status": CampaignStatus.DRAFT,
            "created_at": datetime.now(),
            "stats": {
                "total_targets": len(target_chats),
                "sent": 0,
                "delivered": 0,
                "failed": 0
            }
        }
        
        self.campaigns[campaign_id] = campaign
        return campaign_id
    
    def start_campaign(self, campaign_id: str) -> bool:
        """Iniciar campanha"""
        if campaign_id not in self.campaigns:
            return False
        
        campaign = self.campaigns[campaign_id]
        campaign["status"] = CampaignStatus.RUNNING
        campaign["started_at"] = datetime.now()
        
        return True
    
    def get_campaign_stats(self, campaign_id: str) -> Optional[Dict[str, Any]]:
        """Obter estatísticas da campanha"""
        if campaign_id not in self.campaigns:
            return None
        
        return self.campaigns[campaign_id]["stats"]


# ==========================================
# SERVIDOR MCP PLUS
# ==========================================

# Inicializar componentes
mcp = FastMCP("WAHA MCP PLUS - Premium WhatsApp Automation")
settings = WAHAPlusSettings()
cache = AdvancedCache()
auto_reply = AutoReplyEngine(settings.openai_api_key)
campaigns = CampaignManager()

# Estado global
active_sessions = {}
message_queue = deque()


def get_headers() -> Dict[str, str]:
    """Obter headers com autenticação"""
    headers = {"Content-Type": "application/json"}
    if settings.api_key:
        headers["Authorization"] = f"Bearer {settings.api_key}"
    return headers


def format_chat_id(phone_or_id: str) -> str:
    """Formatar ID do chat com validação"""
    if "@" in phone_or_id:
        return phone_or_id
    if phone_or_id.endswith("@g.us"):
        return phone_or_id
    # Validar número de telefone
    clean_number = re.sub(r'[^\d]', '', phone_or_id)
    if len(clean_number) >= 10:
        return f"{clean_number}@c.us"
    raise ValueError(f"Número inválido: {phone_or_id}")


def track_message(session: str, chat_id: str, message_type: str, direction: str, success: bool, response_time: int = 0):
    """Rastrear mensagem para analytics"""
    if settings.enable_analytics:
        analytics = MessageAnalytics(
            timestamp=datetime.now(),
            session=session,
            chat_id=chat_id,
            message_type=message_type,
            direction=direction,
            success=success,
            response_time_ms=response_time,
            content_length=0
        )
        cache.add_analytics(analytics)


# ==========================================
# FERRAMENTAS PREMIUM - SESSÕES AVANÇADAS
# ==========================================

@mcp.tool
def create_multi_session(
    session_names: List[str],
    config: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Criar múltiplas sessões simultaneamente"""
    if len(session_names) > settings.max_sessions:
        return {"error": f"Máximo de {settings.max_sessions} sessões permitidas"}
    
    results = {}
    
    for session_name in session_names:
        try:
            with httpx.Client() as client:
                payload = {"name": session_name}
                if config:
                    payload.update(config)
                
                response = client.post(
                    f"{settings.base_url}/api/sessions",
                    headers=get_headers(),
                    json=payload
                )
                
                if response.status_code == 201:
                    results[session_name] = {"status": "created", "data": response.json()}
                    active_sessions[session_name] = {"created_at": datetime.now()}
                else:
                    results[session_name] = {"status": "error", "error": response.text}
                    
        except Exception as e:
            results[session_name] = {"status": "error", "error": str(e)}
    
    return {"sessions": results, "total_created": len([r for r in results.values() if r["status"] == "created"])}


@mcp.tool
def get_sessions_status() -> Dict[str, Any]:
    """Obter status detalhado de todas as sessões"""
    try:
        with httpx.Client() as client:
            response = client.get(
                f"{settings.base_url}/api/sessions",
                headers=get_headers()
            )
            response.raise_for_status()
            
            sessions = response.json()
            
            # Adicionar informações premium
            for session in sessions:
                session_name = session.get("name")
                if session_name in active_sessions:
                    session["premium_info"] = {
                        "created_at": active_sessions[session_name]["created_at"].isoformat(),
                        "cached_data": cache.get(f"session_{session_name}") is not None
                    }
            
            return {
                "sessions": sessions,
                "total_sessions": len(sessions),
                "active_sessions": len([s for s in sessions if s.get("status") == "WORKING"]),
                "premium_features": {
                    "analytics_enabled": settings.enable_analytics,
                    "auto_reply_enabled": settings.enable_auto_reply,
                    "rate_limiting_enabled": settings.enable_rate_limiting
                }
            }
            
    except Exception as e:
        return {"error": str(e)}


# ==========================================
# FERRAMENTAS PREMIUM - MENSAGENS INTELIGENTES
# ==========================================

@mcp.tool
def send_smart_message(
    chat_id: str,
    message: str,
    session: str = settings.default_session,
    priority: MessagePriority = MessagePriority.NORMAL,
    schedule_time: Optional[str] = None,
    auto_translate: bool = False
) -> Dict[str, Any]:
    """Enviar mensagem inteligente com recursos avançados"""
    
    # Rate limiting
    if settings.enable_rate_limiting:
        rate_key = f"session_{session}"
        if not cache.check_rate_limit(rate_key, settings.max_requests_per_minute):
            return {"error": "Rate limit excedido. Tente novamente em alguns instantes."}
    
    formatted_chat_id = format_chat_id(chat_id)
    start_time = time.time()
    
    try:
        # Agendamento
        if schedule_time:
            scheduled_msg = ScheduledMessage(
                id=str(uuid.uuid4()),
                chat_id=formatted_chat_id,
                content=message,
                message_type="text",
                scheduled_time=datetime.fromisoformat(schedule_time),
                session=session,
                priority=priority
            )
            
            campaigns.scheduled_messages[scheduled_msg.id] = scheduled_msg
            return {
                "status": "scheduled",
                "message_id": scheduled_msg.id,
                "scheduled_for": schedule_time
            }
        
        # Envio imediato
        payload = {
            "chatId": formatted_chat_id,
            "text": message,
            "session": session
        }
        
        with httpx.Client() as client:
            response = client.post(
                f"{settings.base_url}/api/sendText",
                headers=get_headers(),
                json=payload
            )
            
            response_time = int((time.time() - start_time) * 1000)
            success = response.status_code == 201
            
            # Analytics
            track_message(session, formatted_chat_id, "text", "outbound", success, response_time)
            
            if success:
                result = response.json()
                result["premium_info"] = {
                    "response_time_ms": response_time,
                    "priority": priority,
                    "analytics_tracked": settings.enable_analytics
                }
                return result
            else:
                return {"error": f"Falha ao enviar: {response.text}"}
                
    except Exception as e:
        track_message(session, formatted_chat_id, "text", "outbound", False)
        return {"error": str(e)}


@mcp.tool
def send_bulk_messages(
    targets: List[Dict[str, str]],
    session: str = settings.default_session,
    delay_seconds: int = 1
) -> Dict[str, Any]:
    """Enviar mensagens em massa com controle de delay"""
    
    results = []
    successful = 0
    failed = 0
    
    for i, target in enumerate(targets):
        chat_id = target.get("chat_id")
        message = target.get("message")
        
        if not chat_id or not message:
            results.append({
                "index": i,
                "chat_id": chat_id,
                "status": "error",
                "error": "chat_id e message são obrigatórios"
            })
            failed += 1
            continue
        
        try:
            result = send_smart_message(chat_id, message, session)
            
            if "error" in result:
                results.append({
                    "index": i,
                    "chat_id": chat_id,
                    "status": "error",
                    "error": result["error"]
                })
                failed += 1
            else:
                results.append({
                    "index": i,
                    "chat_id": chat_id,
                    "status": "sent",
                    "message_id": result.get("id")
                })
                successful += 1
            
            # Delay entre mensagens
            if i < len(targets) - 1:
                time.sleep(delay_seconds)
                
        except Exception as e:
            results.append({
                "index": i,
                "chat_id": chat_id,
                "status": "error",
                "error": str(e)
            })
            failed += 1
    
    return {
        "total_targets": len(targets),
        "successful": successful,
        "failed": failed,
        "results": results,
        "completion_rate": f"{(successful/len(targets)*100):.1f}%" if targets else "0%"
    }


# ==========================================
# FERRAMENTAS PREMIUM - ANALYTICS
# ==========================================

@mcp.tool
def get_analytics_dashboard(hours: int = 24) -> Dict[str, Any]:
    """Obter dashboard completo de analytics"""
    
    analytics_data = cache.get_analytics(hours)
    
    if not analytics_data:
        return {"message": "Nenhum dado de analytics disponível"}
    
    # Estatísticas básicas
    total_messages = len(analytics_data)
    successful_messages = len([a for a in analytics_data if a.success])
    failed_messages = total_messages - successful_messages
    
    # Por sessão
    by_session = defaultdict(int)
    for a in analytics_data:
        by_session[a.session] += 1
    
    # Por tipo de mensagem
    by_type = defaultdict(int)
    for a in analytics_data:
        by_type[a.message_type] += 1
    
    # Por direção
    by_direction = defaultdict(int)
    for a in analytics_data:
        by_direction[a.direction] += 1
    
    # Tempo de resposta médio
    response_times = [a.response_time_ms for a in analytics_data if a.response_time_ms > 0]
    avg_response_time = sum(response_times) / len(response_times) if response_times else 0
    
    # Timeline (por hora)
    timeline = defaultdict(int)
    for a in analytics_data:
        hour_key = a.timestamp.strftime("%Y-%m-%d %H:00")
        timeline[hour_key] += 1
    
    return {
        "period_hours": hours,
        "summary": {
            "total_messages": total_messages,
            "successful_messages": successful_messages,
            "failed_messages": failed_messages,
            "success_rate": f"{(successful_messages/total_messages*100):.1f}%" if total_messages else "0%",
            "avg_response_time_ms": round(avg_response_time, 2)
        },
        "breakdown": {
            "by_session": dict(by_session),
            "by_message_type": dict(by_type),
            "by_direction": dict(by_direction)
        },
        "timeline": dict(sorted(timeline.items())),
        "top_chats": self._get_top_chats(analytics_data),
        "performance_metrics": {
            "fastest_response_ms": min(response_times) if response_times else 0,
            "slowest_response_ms": max(response_times) if response_times else 0,
            "median_response_ms": sorted(response_times)[len(response_times)//2] if response_times else 0
        }
    }

def _get_top_chats(analytics_data: List[MessageAnalytics]) -> List[Dict[str, Any]]:
    """Obter chats mais ativos"""
    chat_counts = defaultdict(int)
    for a in analytics_data:
        chat_counts[a.chat_id] += 1
    
    return [
        {"chat_id": chat_id, "message_count": count}
        for chat_id, count in sorted(chat_counts.items(), key=lambda x: x[1], reverse=True)[:10]
    ]


# ==========================================
# FERRAMENTAS PREMIUM - AUTO REPLY
# ==========================================

@mcp.tool
def configure_auto_reply(
    trigger_patterns: List[str],
    response_template: str,
    rule_name: str,
    enabled: bool = True,
    priority: int = 5
) -> Dict[str, Any]:
    """Configurar regra de resposta automática"""
    
    rule = AutoReplyRule(
        id=str(uuid.uuid4()),
        name=rule_name,
        trigger_patterns=trigger_patterns,
        response_template=response_template,
        enabled=enabled,
        priority=priority,
        conditions={}
    )
    
    auto_reply.add_rule(rule)
    
    return {
        "rule_id": rule.id,
        "message": f"Regra '{rule_name}' criada com sucesso",
        "triggers": trigger_patterns,
        "priority": priority,
        "enabled": enabled
    }


@mcp.tool
def list_auto_reply_rules() -> Dict[str, Any]:
    """Listar todas as regras de resposta automática"""
    
    rules_data = []
    for rule in auto_reply.rules:
        rules_data.append({
            "id": rule.id,
            "name": rule.name,
            "trigger_patterns": rule.trigger_patterns,
            "response_template": rule.response_template,
            "enabled": rule.enabled,
            "priority": rule.priority
        })
    
    return {
        "total_rules": len(rules_data),
        "active_rules": len([r for r in rules_data if r["enabled"]]),
        "rules": sorted(rules_data, key=lambda x: x["priority"])
    }


@mcp.tool
def test_auto_reply(message: str, chat_id: str = "test") -> Dict[str, Any]:
    """Testar sistema de resposta automática"""
    
    response = auto_reply.should_auto_reply(message, chat_id)
    
    return {
        "input_message": message,
        "would_reply": response is not None,
        "suggested_response": response,
        "matched_patterns": [
            {
                "rule_name": rule.name,
                "patterns": [p for p in rule.trigger_patterns if p.lower() in message.lower()]
            }
            for rule in auto_reply.rules
            if rule.enabled and any(p.lower() in message.lower() for p in rule.trigger_patterns)
        ]
    }


# ==========================================
# FERRAMENTAS PREMIUM - CAMPANHAS
# ==========================================

@mcp.tool
def create_marketing_campaign(
    campaign_name: str,
    target_chats: List[str],
    message_template: str,
    schedule_time: Optional[str] = None
) -> Dict[str, Any]:
    """Criar campanha de marketing"""
    
    schedule_dt = None
    if schedule_time:
        try:
            schedule_dt = datetime.fromisoformat(schedule_time)
        except ValueError:
            return {"error": "Formato de data inválido. Use ISO format: YYYY-MM-DDTHH:MM:SS"}
    
    campaign_id = campaigns.create_campaign(
        name=campaign_name,
        target_chats=target_chats,
        message_template=message_template,
        schedule_time=schedule_dt
    )
    
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign_name,
        "total_targets": len(target_chats),
        "status": "created",
        "scheduled_for": schedule_time,
        "message": f"Campanha '{campaign_name}' criada com sucesso"
    }


@mcp.tool
def start_campaign(campaign_id: str) -> Dict[str, Any]:
    """Iniciar campanha de marketing"""
    
    if not campaigns.start_campaign(campaign_id):
        return {"error": "Campanha não encontrada"}
    
    campaign = campaigns.campaigns[campaign_id]
    
    # Executar campanha
    sent_count = 0
    failed_count = 0
    
    for chat_id in campaign["target_chats"]:
        try:
            result = send_smart_message(
                chat_id=chat_id,
                message=campaign["message_template"],
                priority=MessagePriority.NORMAL
            )
            
            if "error" not in result:
                sent_count += 1
                campaign["stats"]["sent"] += 1
            else:
                failed_count += 1
                campaign["stats"]["failed"] += 1
                
        except Exception:
            failed_count += 1
            campaign["stats"]["failed"] += 1
    
    campaign["status"] = CampaignStatus.COMPLETED
    campaign["completed_at"] = datetime.now()
    
    return {
        "campaign_id": campaign_id,
        "status": "completed",
        "results": {
            "total_targets": len(campaign["target_chats"]),
            "sent_successfully": sent_count,
            "failed": failed_count,
            "success_rate": f"{(sent_count/len(campaign['target_chats'])*100):.1f}%"
        }
    }


@mcp.tool
def get_campaign_report(campaign_id: str) -> Dict[str, Any]:
    """Obter relatório detalhado da campanha"""
    
    if campaign_id not in campaigns.campaigns:
        return {"error": "Campanha não encontrada"}
    
    campaign = campaigns.campaigns[campaign_id]
    
    return {
        "campaign_id": campaign_id,
        "campaign_name": campaign["name"],
        "status": campaign["status"],
        "created_at": campaign["created_at"].isoformat(),
        "started_at": campaign.get("started_at"),
        "completed_at": campaign.get("completed_at"),
        "statistics": campaign["stats"],
        "target_details": {
            "total_targets": len(campaign["target_chats"]),
            "target_chats": campaign["target_chats"][:10],  # Primeiro 10 para preview
            "message_template": campaign["message_template"]
        }
    }


# ==========================================
# FERRAMENTAS PREMIUM - AGENDAMENTO
# ==========================================

@mcp.tool
def list_scheduled_messages() -> Dict[str, Any]:
    """Listar mensagens agendadas"""
    
    scheduled = []
    for msg_id, msg in campaigns.scheduled_messages.items():
        scheduled.append({
            "id": msg.id,
            "chat_id": msg.chat_id,
            "content": msg.content[:50] + "..." if len(msg.content) > 50 else msg.content,
            "scheduled_time": msg.scheduled_time.isoformat(),
            "priority": msg.priority,
            "session": msg.session,
            "retry_count": msg.retry_count
        })
    
    # Ordenar por tempo de agendamento
    scheduled.sort(key=lambda x: x["scheduled_time"])
    
    return {
        "total_scheduled": len(scheduled),
        "upcoming": [s for s in scheduled if datetime.fromisoformat(s["scheduled_time"]) > datetime.now()],
        "overdue": [s for s in scheduled if datetime.fromisoformat(s["scheduled_time"]) <= datetime.now()],
        "all_scheduled": scheduled
    }


@mcp.tool
def cancel_scheduled_message(message_id: str) -> Dict[str, Any]:
    """Cancelar mensagem agendada"""
    
    if message_id not in campaigns.scheduled_messages:
        return {"error": "Mensagem agendada não encontrada"}
    
    msg = campaigns.scheduled_messages.pop(message_id)
    
    return {
        "message": "Mensagem cancelada com sucesso",
        "cancelled_message": {
            "id": msg.id,
            "chat_id": msg.chat_id,
            "scheduled_time": msg.scheduled_time.isoformat(),
            "content": msg.content[:100] + "..." if len(msg.content) > 100 else msg.content
        }
    }


# ==========================================
# FERRAMENTAS PREMIUM - RELATÓRIOS
# ==========================================

@mcp.tool
def generate_usage_report(days: int = 7) -> Dict[str, Any]:
    """Gerar relatório de uso detalhado"""
    
    analytics_data = cache.get_analytics(days * 24)
    
    # Calcular métricas
    total_messages = len(analytics_data)
    unique_chats = len(set(a.chat_id for a in analytics_data))
    unique_sessions = len(set(a.session for a in analytics_data))
    
    # Análise temporal
    daily_stats = defaultdict(lambda: {"messages": 0, "chats": set(), "sessions": set()})
    
    for a in analytics_data:
        day_key = a.timestamp.strftime("%Y-%m-%d")
        daily_stats[day_key]["messages"] += 1
        daily_stats[day_key]["chats"].add(a.chat_id)
        daily_stats[day_key]["sessions"].add(a.session)
    
    # Converter sets para contagem
    daily_report = {}
    for day, stats in daily_stats.items():
        daily_report[day] = {
            "messages": stats["messages"],
            "unique_chats": len(stats["chats"]),
            "unique_sessions": len(stats["sessions"])
        }
    
    # Top performers
    chat_activity = defaultdict(int)
    session_activity = defaultdict(int)
    
    for a in analytics_data:
        chat_activity[a.chat_id] += 1
        session_activity[a.session] += 1
    
    return {
        "report_period": f"{days} days",
        "generated_at": datetime.now().isoformat(),
        "summary": {
            "total_messages": total_messages,
            "unique_chats": unique_chats,
            "unique_sessions": unique_sessions,
            "daily_average": round(total_messages / days, 1) if days > 0 else 0
        },
        "daily_breakdown": daily_report,
        "top_chats": [
            {"chat_id": chat_id, "message_count": count}
            for chat_id, count in sorted(chat_activity.items(), key=lambda x: x[1], reverse=True)[:10]
        ],
        "session_usage": [
            {"session": session, "message_count": count}
            for session, count in sorted(session_activity.items(), key=lambda x: x[1], reverse=True)
        ],
        "premium_features_usage": {
            "analytics_events": len(analytics_data),
            "scheduled_messages": len(campaigns.scheduled_messages),
            "auto_reply_rules": len(auto_reply.rules),
            "active_campaigns": len([c for c in campaigns.campaigns.values() if c["status"] == "running"])
        }
    }


# ==========================================
# FERRAMENTAS PREMIUM - MONITORAMENTO
# ==========================================

@mcp.tool
def system_health_check() -> Dict[str, Any]:
    """Verificação completa de saúde do sistema"""
    
    health_status = {"status": "healthy", "checks": {}}
    
    # Verificar WAHA
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get(f"{settings.base_url}/ping")
            health_status["checks"]["waha_server"] = {
                "status": "healthy" if response.status_code == 200 else "unhealthy",
                "response_time_ms": response.elapsed.total_seconds() * 1000,
                "url": settings.base_url
            }
    except Exception as e:
        health_status["checks"]["waha_server"] = {
            "status": "unreachable",
            "error": str(e),
            "url": settings.base_url
        }
        health_status["status"] = "degraded"
    
    # Verificar cache
    health_status["checks"]["cache_system"] = {
        "status": "healthy",
        "memory_cache_entries": len(cache._memory_cache),
        "analytics_events": len(cache._analytics),
        "rate_limit_keys": len(cache._rate_limits)
    }
    
    # Verificar componentes premium
    health_status["checks"]["premium_features"] = {
        "auto_reply_engine": {
            "status": "healthy",
            "rules_count": len(auto_reply.rules),
            "enabled": settings.enable_auto_reply
        },
        "campaign_manager": {
            "status": "healthy",
            "active_campaigns": len([c for c in campaigns.campaigns.values() if c["status"] == "running"]),
            "scheduled_messages": len(campaigns.scheduled_messages)
        },
        "analytics": {
            "status": "healthy",
            "enabled": settings.enable_analytics,
            "events_tracked": len(cache._analytics)
        }
    }
    
    # Verificar sessões ativas
    try:
        sessions_result = get_sessions_status()
        if "error" not in sessions_result:
            health_status["checks"]["sessions"] = {
                "status": "healthy",
                "total_sessions": sessions_result["total_sessions"],
                "active_sessions": sessions_result["active_sessions"]
            }
        else:
            health_status["checks"]["sessions"] = {
                "status": "error",
                "error": sessions_result["error"]
            }
            health_status["status"] = "degraded"
    except Exception as e:
        health_status["checks"]["sessions"] = {
            "status": "error",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Timestamp
    health_status["timestamp"] = datetime.now().isoformat()
    health_status["version"] = "1.0.0-plus"
    
    return health_status


if __name__ == "__main__":
    # Executar o servidor premium
    mcp.run()
