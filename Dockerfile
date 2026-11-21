# Mech Royale bot (mechfight/1). Standard library only: nothing to install, nothing fetched at runtime.
# The match runs it with no network, a read-only root (writable /tmp), 1 CPU, 512 MB, uid 65534, map at /arena.
FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /bot
COPY bot/ /bot/
COPY arena/ /bot/arena/
RUN python3 -m compileall -q /bot
ENTRYPOINT ["python3", "-u", "/bot/main.py"]
