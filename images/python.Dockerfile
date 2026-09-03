FROM ghcr.io/astral-sh/uv:python3.12-bookworm

ARG REPO_URL
ARG REPO_SHA
ARG INSTALL_CMD
ARG CLAUDE_VERSION=2.1.259
ARG COPILOT_VERSION=1.0.82

RUN apt-get update && apt-get install -y --no-install-recommends \
    git less procps curl ca-certificates jq patch \
    && rm -rf /var/lib/apt/lists/*

RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs && rm -rf /var/lib/apt/lists/*

RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_VERSION} @github/copilot@${COPILOT_VERSION}

RUN git clone ${REPO_URL} /repo && git -C /repo checkout ${REPO_SHA} \
    && git config --global user.email agent@repogym.local \
    && git config --global user.name repogym-agent \
    && git config --global --add safe.directory '*'

# warm the uv cache so trial-time installs in /work take seconds
WORKDIR /repo
RUN ${INSTALL_CMD}

WORKDIR /work
