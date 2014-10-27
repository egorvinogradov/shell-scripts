#!/bin/bash

file=$1

project_root=$HOME/amazinghiring/frontend

cp $file $project_root/extension/chrome/img/favicons/
cp $file $project_root/apps/ah/static/img/favicons/

filename=$(basename "$file")    
extension="${filename##*.}"
filename="${filename%.*}"

link_order_app=$project_root/apps/ah/static/js/link-order.coffee
link_order_extension=$project_root/extension/chrome/js/link-order.coffee

extension_ui_path=$project_root/extension/chrome/css/
interface_ui_path=$project_root/apps/ah/static/css/modules/

cp $link_order_app _temp
sed '$ d' _temp > $link_order_app
rm -f _temp

echo "    \"$filename\"
]" >> $link_order_app

cp $link_order_extension _temp
sed '$ d' _temp > $link_order_extension
rm -f _temp

echo "    \"$filename\"
]" >> $link_order_extension


echo "\n.ah-icon-site_$filename\n    background-image: url('chrome-extension://__MSG_@@extension_id__/img/favicons/$filename.$extension')" >> $extension_ui_path/ui.sass

echo "\n.b-icon-site_$filename\n    background-image: url('/static/img/favicons/$filename.$extension')" >> $interface_ui_path/ui.sass

coffee -cb $link_order
sass $extension_ui_path/ui.sass $extension_ui_path/ui.css
sass $interface_ui_path/ui.sass $interface_ui_path/ui.css
