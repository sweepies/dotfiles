function check_updates
    function check
        echo "Checking for package updates"
        yay --query --upgrades --refresh > $updates_file
    end

    if test ! -f $updates_file
        check
    else
        set time_now (date +%s)
        set last_modified (stat -c %Y $updates_file)

        if test (math $time_now - $last_modified) -ge 259200
            check
        end
    end

    set updates_list (cat $updates_file)

        #for package in $updates_ignore_list
        #    set -a updates_list 
        #end

    set updates_count (echo $updates_list | wc -l)

    if test $updates_count -eq 0
        return
    else if test $updates_count -eq 1
        echo "1 update is available."
    else
        echo "$updates_count updates are available."
    end
end