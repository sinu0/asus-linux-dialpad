#!/usr/bin/env bash

source non_sudo_check.sh

source install_paths.sh

sudo groupadd "dialpad"

sudo usermod -a -G "dialpad" $USER

if [[ $? != 0 ]]; then
    echo "Something went wrong when adding the group dialpad to current user"
    exit 1
else
    echo "Added group dialpad to current user"
fi

sudo mkdir -p "$LOGS_DIR_PATH"
sudo chown -R :dialpad "$LOGS_DIR_PATH"
sudo chmod -R g+w "$LOGS_DIR_PATH"