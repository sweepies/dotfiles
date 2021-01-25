if [ -z $SSH_CONNECTION ] && type code-insiders &> /dev/null
    export EDITOR="code-insiders"
    alias code="code-insiders"
else
    export EDITOR="nano"
end

# WSL specific
if grep --quiet --extended-regexp --ignore-case "(Microsoft|WSL)" /proc/version
    function explorer
        if [ -z $1 ]
            explorer.exe (wslpath -w .)
        else
            explorer.exe (wslpath -w $1)
        end
    end
    alias explore=explorer
end

direnv hook fish | source

# check_updates # gotta fix this
