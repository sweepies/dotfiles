if type keychain &>/dev/null; then
    eval "$(keychain --eval --agents gpg,ssh id_ed25519 3A8457B5)"
fi
