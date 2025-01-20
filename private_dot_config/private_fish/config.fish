direnv hook fish | source

# Configure ssh forwarding
#set -x SSH_AUTH_SOCK $HOME/.ssh/agent.sock
# need `ps -ww` to get non-truncated command for matching
# use square brackets to generate a regex match for the process we want but that doesn't match the grep command running it!
#set ALREADY_RUNNING (ps -auxww | grep -q "[n]piperelay.exe -ei -s //./pipe/openssh-ssh-agent"; echo $status)
#if string match -q --invert "0" $ALREADY_RUNNING ;
#    if test -S $SSH_AUTH_SOCK ;
# not expecting the socket to exist as the forwarding command isn't running (http://www.tldp.org/LDP/abs/html/fto.html)
#        echo "removing previous socket..."
#        rm $SSH_AUTH_SOCK
#    end
#    echo "Starting SSH-Agent relay..."
# setsid to force new session to keep running
# set socat to listen on $SSH_AUTH_SOCK and forward to npiperelay which then forwards to openssh-ssh-agent on windows
#    setsid socat UNIX-LISTEN:$SSH_AUTH_SOCK,fork EXEC:"npiperelay.exe -ei -s //./pipe/openssh-ssh-agent",nofork & # >/dev/null 2>&1
#end

#set normal (set_color normal)
#set magenta (set_color magenta)
#set yellow (set_color yellow)
#set green (set_color green)
#set red (set_color red)
#set gray (set_color -o black)

# Fish git prompt
#set -U __fish_git_prompt_showdirtystate yes
#set -U __fish_git_prompt_showstashstate yes
#set -U __fish_git_prompt_showuntrackedfiles yes
#set -U __fish_git_prompt_showupstream yes
#set __fish_git_prompt_color_branch yellow
#set __fish_git_prompt_color_upstream_ahead green
#set __fish_git_prompt_color_upstream_behind red

# Status Chars
#set __fish_git_prompt_char_dirtystate '⚡'
#set __fish_git_prompt_char_stagedstate '→'
#set __fish_git_prompt_char_untrackedfiles '☡'
#set __fish_git_prompt_char_stashstate '↩'
#set __fish_git_prompt_char_upstream_ahead '+'
#set __fish_git_prompt_char_upstream_behind -


# Created by `pipx` on 2025-01-20 07:00:48
set PATH $PATH /home/sweepy/.local/bin
