# depends on zplugin, opportunistic extras:
# linuxbrew, vscode, keychain, hub, gcloud, httpie, docker, dotenv

source "$HOME/.zplugin/bin/zplugin.zsh"
autoload -Uz _zplugin compinit
(( ${+_comps} )) && _comps[zplugin]=_zplugin

zplugin ice depth"1" multisrc="lib/*.zsh" pick"/dev/null"
zplugin light robbyrussell/oh-my-zsh

zplugin snippet OMZ::themes/lukerandall.zsh-theme

zplugin light zdharma/fast-syntax-highlighting
zplugin light zsh-users/zsh-completions
zplugin light zsh-users/zsh-autosuggestions

zplugin ice as"completion"
zplugin snippet OMZ::plugins/docker/_docker

zplugin ice as"completion"
zplugin snippet OMZ::plugins/httpie/_httpie

plugins=("git" "docker-compose" "dotenv" "command-not-found"
    "extract" "colored-man-pages" "gcloud" "github" "npm")

for p in "${plugins[@]}"; do
   zplugin snippet OMZ::plugins/"$p"/"$p".plugin.zsh
done

compinit
