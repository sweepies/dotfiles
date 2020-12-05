if type keychain &>/dev/null
    keychain --agents gpg,ssh id_ed25519 3A8457B5
else
    echo "keychain not found"
    exit 127
end
