#!/bin/bash

# ./pycharm_restore.sh --backup
# 1. Копирует ~/Library/Preferences/PyCharm20 в ~/PyCharm20
# 2. Удаляет ~/Library/Preferences/PyCharm20
# 3. Копирует нужные настройки в ~/pycharm_cache

# ./pycharm_restore.sh --restore
# 1. Восстанавливает настройки из ~/pycharm_cache
# 2. Удаляет ~/pycharm_cache/ и ~/__pc_options__/

# Вручную установить
# 1. Python interpreter —> ./virtualenvs/.ahfrontend
# 2. Appearance —> Theme —> Dracula
# 3. Editor -> Code Completion -> Parameter Info -> Autopopup in ms
# 4. Code style -> CoffeeScript -> Tab size ( Scheme -> Default (4), Wrapping and braces )
# 5. Editor -> Colors and fonts -> General -> monokai_custom

path="$HOME/Library/Preferences/PyCharm20"
cache_directory="$HOME/pycharm_cache"

if [ "$1" = "--backup" ]
    then
        mkdir $cache_directory
        mkdir "$cache_directory/options"
        backup_source=$path
        backup_target=$cache_directory
    elif [ "$1" = '--restore' ]
    then
        mkdir $path
        mkdir "$path/options"
        backup_source=$cache_directory
        backup_target=$path
    else
        echo "
        Set --backup or --restore option
        "
        exit
fi

option_files="keymap.xml
editor.xml
other.xml
cachedDictionary.xml
notifications.xml
statistics.application.usages.xml
ui.lnf.xml
ide.general.xml
usage.statistics.xml
vcs.xml
colors.scheme.xml
textmate.xml
webServers.xml"

directories="codestyles
keymaps
colors"


for file in $option_files
do
    source_file_path="$backup_source/options/$file"
    target_file_path="$backup_target/options/"
    cp $source_file_path $target_file_path
    echo "Copied to $target_file_path file $source_file_path"
done

for directory in $directories
do
    source_directory_path="$backup_source/$directory"
    target_directory_path="$backup_target/$directory"
    cp -r $source_directory_path $target_directory_path
    echo "Copied to $backup_target directory $source_directory_path"
done

if [ "$1" = "--backup" ]
    then
        cp -r $path "$HOME/__pc_options__"
        rm -rf $path
fi

if [ "$1" = "--restore" ]
    then
        rm -rf "$HOME/pycharm_cache/" && rm -rf "$HOME/__pc_options__/"
fi
