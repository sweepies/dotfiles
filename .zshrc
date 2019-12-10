ANTIGEN=~/antigen.zsh
if [[ ! -f "$ANTIGEN" ]]; then
    echo "Antigen not found, installing.."
    curl -sL git.io/antigen > "$ANTIGEN"
fi
source "$ANTIGEN"

antigen use oh-my-zsh

antigen bundles <<EOBUNDLES
git
docker
command-not-found
extract
colored-man-pages
zsh-users/zsh-completions
zsh-users/zsh-syntax-highlighting
zsh-users/zsh-autosuggestions
EOBUNDLES

antigen theme lukerandall

antigen apply

export PATH="$PATH:$HOME/.local/bin"

if [[ -n $SSH_CONNECTION ]]; then
    export EDITOR='nano'
else
    export EDITOR='code'
fi

alias ls="ls -A"

# init keychain if on local machine
if [[ ! -n $SSH_CONNECTION ]]; then
    eval `keychain --eval --agents gpg,ssh id_ed25519 3A8457B5`
fi

export GPG_TTY=$(tty)

# The next line updates PATH for the Google Cloud SDK.
if [ -f '/home/sweepy/google-cloud-sdk/path.zsh.inc' ]; then . '/home/sweepy/google-cloud-sdk/path.zsh.inc'; fi

# The next line enables shell command completion for gcloud.
if [ -f '/home/sweepy/google-cloud-sdk/completion.zsh.inc' ]; then . '/home/sweepy/google-cloud-sdk/completion.zsh.inc'; fi

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
set -e
if grep -qE "(Microsoft|WSL)" /proc/version &> /dev/null ; then
    explorer() {
        if [[ -z $1 ]]; then
            cwd=$(pwd)
            explorer.exe $(wslpath -w $cwd)
            return 0
        fi
        explorer.exe $(wslpath -w $1)
    }

    export DOCKER_HOST=tcp://localhost:2375
fi
