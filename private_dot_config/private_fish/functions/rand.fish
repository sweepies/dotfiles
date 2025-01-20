#!/usr/bin/env fish

function rand
    set types "hex" "base64" "b64" "chars" "c" "password" "pw" "uuid" "guid"

    if set -q $argv[1]
        printf "Usage: %s TYPE [<AMOUNT>]\n" (status current-command)
        printf "\
Generate random data

Possible types:
  hex
  base64, b64
  chars, c
  password, pw
  uuid, guid

When using encoding types, AMOUNT is in bytes.\n"
        return 126
    end

    if not contains $argv[1] $types
        printf "%s: invalid type: '%s'\n" (status current-command) "$argv[1]"
        return 22
    end

    if not string match -q $argv[1] "password" "pw" "uuid" "guid"
        if not string match -rq '^[0-9]+$' $argv[2]
            printf "%s: invalid number: '%s'\n" (status current-command) "$argv[2]"
            return 22
        end
    end


    switch $argv[1]
        case "hex"
            set data (head -c "$argv[2]" < /dev/urandom | xxd -ps | tr -d '\n')
        case "base64" "b64"
            set data (head -c "$argv[2]" < /dev/urandom | base64)
        case "chars" "c"
            set data (tr -cd "[:alnum:]" < /dev/urandom | head -c "$argv[2]")
        case "password" "pw"
            set data (tr -cd "[:alnum:][:punct:]" < /dev/urandom | head -c 24)
        case "uuid" "guid"
            set data (uuidgen --random)

    end

    printf "%s\n" "$data"
end
