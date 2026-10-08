function fish_greeting
    if set -q fish_startup_start_time
        # Hand startup time to the first prompt render instead of printing a greeting.
        set -g __fish_startup_duration_ms (math (gdate +%s%3N) - $fish_startup_start_time)
        set -e fish_startup_start_time
    end
end
