# Dockerfile para WAHA MCP Server
FROM python:3.11-slim

# Definir diretório de trabalho
WORKDIR /app

# Instalar dependências do sistema
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copiar arquivos de dependências
COPY pyproject.toml ./
COPY uv.lock ./

# Instalar uv para gerenciamento de dependências
RUN pip install uv

# Instalar dependências do projeto
RUN uv sync --frozen

# Copiar código fonte
COPY src/ ./src/
COPY examples/ ./examples/
COPY server.py ./

# Criar diretório para logs
RUN mkdir -p /app/logs

# Expor porta padrão do MCP
EXPOSE 8000

# Definir variáveis de ambiente padrão
ENV WAHA_BASE_URL=http://localhost:3000
ENV WAHA_DEFAULT_SESSION=default
ENV PYTHONPATH=/app/src

# Comando padrão - executar o servidor WAHA MCP
CMD ["uv", "run", "python", "server.py"]
