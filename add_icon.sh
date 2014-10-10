#!/bin/bash

file=$1

project_root=$HOME/amazinghiring/frontend

cp $file $project_root/extension/chrome/img/favicons/
cp $file $project_root/apps/ah/static/img/favicons/

filename=$(basename "$file")    
extension="${filename##*.}"
filename="${filename%.*}"

link_order=$project_root/apps/ah/static/js/link-order.coffee
extension_ui_path=$project_root/extension/chrome/css/
interface_ui_path=$project_root/apps/ah/static/css/modules/

cp $link_order _temp
sed '$ d' _temp > $link_order
rm -f _temp

echo "    \"$filename\"
]" >> $link_order

echo "\n.ah-icon-site_$filename\n    background-image: url('chrome-extension://__MSG_@@extension_id__/img/favicons/$filename.$extension')" >> $extension_ui_path/ui.sass

echo "\n.b-icon-site_$filename\n    background-image: url('/static/img/favicons/$filename.$extension')" >> $interface_ui_path/ui.sass

coffee -cb $link_order
sass $extension_ui_path/ui.sass $extension_ui_path/ui.css
sass $interface_ui_path/ui.sass $interface_ui_path/ui.css
