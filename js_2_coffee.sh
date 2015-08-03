#!/bin/bash
# Converts .js files to .coffee recursively
# Usage: run ./js_2_coffee.sh in the parent directory

for FILE in `find . -name "*.js" -type f -o -path './node_modules' -prune -o -path './components' -prune -o -path './bower_components' -prune`
do 
    if [ -e $FILE ] ; then        
        COFFEE=${FILE//.js/.coffee}

        echo "converting ${FILE} to ${COFFEE}"
        js2coffee "$FILE" > "$COFFEE"
    else     
        echo "File: {$1} does not exist!"
    fi
done
