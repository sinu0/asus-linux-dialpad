#!/usr/bin/env bash

# Shared by the install scripts. The installer runs unattended unless it is
# started with --interactive (or INTERACTIVE=1); every question then takes
# its default answer.

if [ -z "$INTERACTIVE" ]; then
    INTERACTIVE=0
    for ARG in "$@"; do
        case "$ARG" in
            -i|--interactive) INTERACTIVE=1 ;;
        esac
    done
fi

# ask "Question" y|n  ->  status 0 for yes
ask() {
    local question=$1
    local default=${2:-n}
    local hint="[y/N]"
    [ "$default" = "y" ] && hint="[Y/n]"

    if [ "$INTERACTIVE" != "1" ]; then
        echo "$question -> $default"
        [ "$default" = "y" ]
        return
    fi

    local reply
    read -r -p "$question $hint " reply
    reply=${reply:-$default}
    [[ "$reply" =~ ^[Yy]([Ee][Ss])?$ ]]
}

is_gnome() {
    [[ "${XDG_CURRENT_DESKTOP,,}" == *gnome* ]] && command -v gnome-extensions >/dev/null 2>&1
}
