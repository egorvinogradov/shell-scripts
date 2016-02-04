#!/bin/bash

echo "Running local summa-test"

export LG_HOME="/Users/egor/leadgenius"
export PREMIERE_ROOT="$LG_HOME/Premiere"
export SUMMA_TEST_ROOT="$LG_HOME/summa-test"

source /usr/local/bin/virtualenvwrapper.sh
workon leadgenius
$SUMMA_TEST_ROOT/test.sh
$SUMMA_TEST_ROOT/integration_tests.py
