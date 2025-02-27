function fish_prompt --description 'Write out the prompt'
    set -l last_pipestatus $pipestatus
    set -l last_status $status
    set -l normal (set_color normal)

    set -l color_cwd $fish_color_cwd
    set -l prefix '['
    set -l suffix ']'

    # Get docker context only if the command succeeds
    set -l docker_context ""
    if command -sq docker
        set -l docker_context_output (docker context show 2>/dev/null)
        if test $status -eq 0
            set docker_context " $docker_context_output"
        end
    end

    # If we're running via SSH, change the host color.
    set -l color_host $fish_color_host
    if set -q SSH_TTY
        set color_host $fish_color_host_remote
    end

    # Write pipestatus
    set -l prompt_status (__fish_print_pipestatus " [" "]" "|" (set_color $fish_color_status) (set_color --bold $fish_color_status) $last_pipestatus)

    echo -n -s $prefix (set_color $fish_color_user) "$USER" $normal ' ' (set_color $color_cwd) (prompt_pwd) $normal (fish_vcs_prompt) $docker_context $normal $prompt_status $suffix " "
end
