#!/bin/bash

echo "Running battery watch"

battery_limit=89.1


battery_status=`ioreg -l | grep -i capacity | tr '\n' ' | ' | awk '{printf("%.2f\n", $10/$5 * 100)}'`



echo ">>> (2) $((battery_status + 1))"

if [ $((battery_status + 1)) -le 9 ]; then
  echo "1 true"
else
  echo "0 false"
fi

# while true; do
#   battery_status=`ioreg -l | grep -i capacity | tr '\n' ' | ' | awk '{printf("%.2f\n", $10/$5 * 100)}'`
#   if [ $(( $battery_status )) -le "89" ]; then
#     echo "Status discharged: $battery_status"
#   fi
#   sleep 2
# done


# ioreg -l | grep -i capacity | tr '\n' ' | ' | awk '{printf("%.2f\n", $10/$5 * 100)}'


# ioreg -l | grep -i capacity | tr '\n' ' | ' | awk '{printf("%.2f\n", $10/$5 * 100)}'

# ioreg -l | grep -i capacity | tr '\n' ' | ' | awk '{printf("%.2f\n", $10/$5 * 100)}'

