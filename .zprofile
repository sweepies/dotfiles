FPATH="/home/linuxbrew/.linuxbrew/share/zsh/site-functions:$FPATH"

if [[ -d "/home/linuxbrew" ]]; then
    # `brew shellenv`
    export HOMEBREW_PREFIX="/home/linuxbrew/.linuxbrew"
    export HOMEBREW_CELLAR="/home/linuxbrew/.linuxbrew/Cellar"
    export HOMEBREW_REPOSITORY="/home/linuxbrew/.linuxbrew/Homebrew"
    export PATH="/home/linuxbrew/.linuxbrew/bin:/home/linuxbrew/.linuxbrew/sbin${PATH+:$PATH}"
    export MANPATH="/home/linuxbrew/.linuxbrew/share/man${MANPATH+:$MANPATH}:"
    export INFOPATH="/home/linuxbrew/.linuxbrew/share/info${INFOPATH+:$INFOPATH}"
fi

export PATH="$HOME/.local/bin:$PATH"

if [[ -n $SSH_CONNECTION ]]; then
    export EDITOR='nano'
else
    if type code &> /dev/null; then
        export EDITOR='code-insiders'
    fi
    if type keychain &> /dev/null; then
        eval "$(keychain --eval --agents gpg,ssh id_ed25519 3A8457B5)"
    fi
fi

alias ls="ls -A"
alias code="code-insiders"

if type hub &> /dev/null; then
    # `hub alias -s`
    alias git=hub
fi

export CLOUDSDK_PYTHON="python3"

# WSL specific
if grep -qE "(Microsoft|WSL)" /proc/version &> /dev/null; then
    explorer() {
        if [[ -z $1 ]]; then
            cwd=$(pwd)
            explorer.exe $(wslpath -w "$cwd")
            return 0
        fi
        explorer.exe $(wslpath -w "$1")
    }

    export DOCKER_HOST=tcp://localhost:2375
fi