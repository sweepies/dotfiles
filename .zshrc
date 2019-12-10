source <(antibody init)

antibody bundle <<EOBUNDLES
robbyrussell/oh-my-zsh path:plugins/git
robbyrussell/oh-my-zsh path:plugins/docker
robbyrussell/oh-my-zsh path:plugins/docker-compose
robbyrussell/oh-my-zsh path:plugins/dotenv
robbyrussell/oh-my-zsh path:plugins/command-not-found
robbyrussell/oh-my-zsh path:plugins/extract
robbyrussell/oh-my-zsh path:plugins/colored-man-pages
robbyrussell/oh-my-zsh path:plugins/gcloud
robbyrussell/oh-my-zsh path:plugins/github
robbyrussell/oh-my-zsh path:plugins/httpie
robbyrussell/oh-my-zsh path:plugins/npm
robbyrussell/oh-my-zsh path:plugins/gcloud
robbyrussell/oh-my-zsh path:lib
robbyrussell/oh-my-zsh path:themes/lukerandall.zsh-theme
zsh-users/zsh-syntax-highlighting
zsh-users/zsh-completions
zsh-users/zsh-autosuggestions
EOBUNDLES

export GPG_TTY=$(tty)

if [[ -n $SSH_CONNECTION ]]; then
    export EDITOR='nano'
else
    export EDITOR='code'
    eval `keychain --eval --agents gpg,ssh id_ed25519 3A8457B5`
fi

alias ls="ls -A"

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
