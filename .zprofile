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

if [[ -n $SSH_CONNECTION ]]; then
    export EDITOR='nano'
else
    if type code &> /dev/null; then
        export EDITOR='code'
    fi
    if type keychain &> /dev/null; then
        eval "$(keychain --eval --agents gpg,ssh id_ed25519 3A8457B5)"
    fi
fi

alias ls="ls -A"

if type hub &> /dev/null; then
    # `hub alias -s`
    alias git=hub
fi

export CLOUDSDK_PYTHON="python3"

### functions ###
rand() {
    types=("hex" "base64" "b64" "chars" "c")

    if [[ -z $1 ]]; then
        cat << EOF
Usage: $0 TYPE AMOUNT
Generate random data

AMOUNT is in bytes.

Possible types:
  hex
  base64, b64
  chars, c
EOF
        return 126
    fi

    if ! [[ "${types[*]}" =~ $1 ]]; then
        echo "$0: invalid type: '$1'"
        return 1
    fi

    if ! [[ $2 =~ ^[0-9]+$ ]]; then
        echo "$0: invalid number: '$2'"
        return 1
    fi

    case "$1" in
        "hex") data=$(head -c "$2" < /dev/urandom | xxd -p) ;;
        "base64" | "b64") data=$(head -c "$2" < /dev/urandom | base64) ;;
        "chars" | "c") data=$(tr -dc a-zA-Z0-9 < /dev/urandom | head -c "$2") ;;
    esac

    printf "%s\n" "$data"
}

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