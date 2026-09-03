FROM node:22-bookworm

ARG REPO_URL
ARG REPO_SHA
ARG INSTALL_CMD
ARG CLAUDE_VERSION=2.1.259
ARG COPILOT_VERSION=1.0.82
ARG AIDER_VERSION=0.86.2

ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0

RUN apt-get update && apt-get install -y --no-install-recommends \
    less procps jq patch ca-certificates \
    && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION} @github/copilot@${COPILOT_VERSION}

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
RUN uv tool install --python 3.12 aider-chat==${AIDER_VERSION} \
    && ln -sf /root/.local/bin/aider /usr/local/bin/aider

RUN corepack enable \
    && git config --global user.email agent@repogym.local \
    && git config --global user.name repogym-agent \
    && git config --global --add safe.directory '*'

RUN git clone ${REPO_URL} /repo && git -C /repo checkout ${REPO_SHA}

WORKDIR /repo
RUN printf '%s\n' "${INSTALL_CMD}" > /install.sh && bash /install.sh

WORKDIR /work
