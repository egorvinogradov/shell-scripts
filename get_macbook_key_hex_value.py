# Example:
# Remap (swap) keys on Macbook.
# python get_macbook_key_hex_value.py 0xE6 0x50     # Example: swap Right Alt and Left Arrow
#
# List of keyboard values:
# https://developer.apple.com/library/content/technotes/tn2450/_index.html#//apple_ref/doc/uid/DTS40017618-CH1-KEY_TABLE_USAGES
#
# How to remap Mac keys:
# https://apple.stackexchange.com/a/283253


import sys
import os

key_from = sys.argv[1]
key_to = sys.argv[2]

def convert(val):
  int_val = int(val, 16)
  ref = '0x700000000'
  int_ref = int(ref, 16)
  return hex(int_ref | int_val)

def remap_keys(hex_from, hex_to):
  cmd = """hidutil property --set '{"UserKeyMapping":
    [{"HIDKeyboardModifierMappingSrc":%s,
      "HIDKeyboardModifierMappingDst":%s},
     {"HIDKeyboardModifierMappingSrc":%s,
      "HIDKeyboardModifierMappingDst":%s}]
}'""" % (hex_from, hex_to, hex_to, hex_from)
  print cmd
  os.system(cmd)


if (key_from and key_to):
  hex_from = convert(key_from)
  hex_to = convert(key_to)
  remap_keys(hex_from, hex_to)
