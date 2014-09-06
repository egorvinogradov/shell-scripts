#!/bin/bash

# Usage:
# To switch config to master: ./set_django_config.sh master
# To switch to another config: ./set_django_config.sh <port>

current_config_path="$HOME/amazinghiring/config/sysconfig.json"

config_name="sysconfig-django-$1-debug.json"

if [ "$1" = "master" ]
    then
        config_name="sysconfig-master-debug.json"
        echo "Switched config to master debug"
    else
        echo "Switched config to $config_name"
fi

if [ -a "$current_config_path" ]
    then
        rm $current_config_path
fi

ln -s /common/configs/$config_name $current_config_path
