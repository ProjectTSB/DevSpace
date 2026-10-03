FROM mcr.microsoft.com/devcontainers/base:ubuntu

ARG USERNAME=vscode

# statusline.sh の実行時依存(jq)を保証する
RUN apt-get update \
  && apt-get install -y --no-install-recommends jq openjdk-17-jre-headless python3 \
  && rm -rf /var/lib/apt/lists/*

# Used to persist bash history as per https://code.visualstudio.com/remote/advancedcontainers/persist-bash-history
RUN SNIPPET="export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
  && mkdir /commandhistory \
  && touch /commandhistory/.bash_history \
  && chown -R $USERNAME /commandhistory \
  && echo "$SNIPPET" >> "/home/$USERNAME/.bashrc"

# Install codex
RUN curl -fsSL https://chatgpt.com/codex/install.sh \
    -o /tmp/install-codex.sh \
  && CODEX_NON_INTERACTIVE=true \
    CODEX_HOME=/opt/codex \
    CODEX_INSTALL_DIR=/usr/local/bin \
    sh /tmp/install-codex.sh \
  && rm /tmp/install-codex.sh

# Used to store Claude configuration files
RUN mkdir /home/$USERNAME/.claude && chown -R $USERNAME /home/$USERNAME/.claude
# Used to store Codex configuration files
RUN mkdir /home/$USERNAME/.codex && chown -R $USERNAME /home/$USERNAME/.codex
# Initialize the GitHub CLI volume with a private, user-writable directory.
RUN install -d -m 0700 -o $USERNAME -g $USERNAME /home/$USERNAME/.config/gh

# Load AI entrypoint functions from the mounted workspace in interactive Bash.
RUN echo '[ ! -r /workspaces/DevSpace/scripts/ai-shell.bash ] || . /workspaces/DevSpace/scripts/ai-shell.bash' >> /etc/bash.bashrc
