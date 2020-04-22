source ~/.zinit/bin/zinit.zsh
autoload -Uz _zinit
(( ${+_comps} )) && _comps[zinit]=_zinit

zinit ice depth"1" multisrc="lib/*.zsh" pick"/dev/null"

zinit light robbyrussell/oh-my-zsh
zinit snippet OMZ::themes/lukerandall.zsh-theme

zinit light zsh-users/zsh-autosuggestions
zinit light zdharma/fast-syntax-highlighting

zinit ice as"completions" blockf
zinit light zsh-users/zsh-completions

plugins=("dotenv" "extract" "colored-man-pages")

for p in "${plugins[@]}"; do
   zinit snippet OMZ::plugins/"$p"/"$p".plugin.zsh
done

zinit compinit > /dev/null

export N_PREFIX="$HOME/n"; [[ :$PATH: == *":$N_PREFIX/bin:"* ]] || PATH+=":$N_PREFIX/bin"  # Added by n-install (see http://git.io/n-install-repo).

if [[ -z $SSH_CONNECTION ]] && type code-insiders &> /dev/null; then
    export EDITOR='code-insiders'
else
    export EDITOR='nano'
fi

alias ls="ls --almost-all"
alias code="code-insiders"

if type hub &> /dev/null; then
    alias git=hub
fi

# WSL specific
if grep --quiet --extended-regexp --ignore-case "(Microsoft|WSL)" /proc/version; then
    explorer() {
        if [[ -z $1 ]]; then
            explorer.exe $(wslpath -w .)
        else
            explorer.exe $(wslpath -w "$1")
        fi
    }
fi

export PATH="$PATH:$HOME/.local/bin"
