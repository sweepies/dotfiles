function fish_prompt --description 'Write out the prompt'
    set -l last_pipestatus $pipestatus
    set -lx __fish_last_status $status
    set -l normal (set_color --reset)

    # Color the prompt differently when we're root.
    set -l color_cwd $fish_color_cwd
    set -l suffix '>'
    if functions -q fish_is_root_user; and fish_is_root_user
        if set -q fish_color_cwd_root
            set color_cwd $fish_color_cwd_root
        end
        set suffix '#'
    end

    # Write pipestatus.
    # If the status was carried over (if no command is issued or if `set` leaves the status untouched), don't bold it.
    set -l bold_flag --bold
    set -q __fish_prompt_status_generation; or set -g __fish_prompt_status_generation $status_generation
    if test $__fish_prompt_status_generation = $status_generation
        set bold_flag
    end
    set __fish_prompt_status_generation $status_generation
    set -l status_color (set_color $fish_color_status)
    set -l statusb_color (set_color $bold_flag $fish_color_status)
    set -l prompt_status (__fish_print_pipestatus "[" "]" "|" "$status_color" "$statusb_color" $last_pipestatus)

    set -l duration_ms 0
    if set -q __fish_startup_duration_ms
        set duration_ms $__fish_startup_duration_ms
        set -e __fish_startup_duration_ms
    else if set -q CMD_DURATION
        set duration_ms $CMD_DURATION
    end

    set -l duration_display $duration_ms'ms'
    if test $duration_ms -ge 1000
        set -l duration_seconds (math --scale=2 "$duration_ms / 1000")
        set duration_display (string replace -r '\.?0+$' '' -- $duration_seconds)'s'
    end

    echo -n -s $duration_display " " (set_color $color_cwd) (prompt_pwd) $normal (fish_vcs_prompt) $normal $prompt_status $suffix " "
end
