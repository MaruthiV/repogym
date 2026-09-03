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

# uv's tool bin dir is /usr/local/bin in this base image, no symlink needed
ARG AIDER_VERSION=0.86.2
RUN uv tool install aider-chat==${AIDER_VERSION}

# shared layer across all repo images (identical instruction -> cached once)
RUN uv tool install openhands-ai || echo "openhands install failed, adapter will report"

RUN git clone ${REPO_URL} /repo && git -C /repo checkout ${REPO_SHA} \
    && git config --global user.email agent@repogym.local \
    && git config --global user.name repogym-agent \
    && git config --global --add safe.directory '*'

# warm the uv cache so trial-time installs in /work take seconds
# install cmd goes through a script file so && works despite buildkit arg quoting
WORKDIR /repo
RUN printf '%s\n' "${INSTALL_CMD}" > /install.sh && bash /install.sh

WORKDIR /work
