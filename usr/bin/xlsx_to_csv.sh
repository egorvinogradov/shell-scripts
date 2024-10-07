#!/bin/bash

# Check if the input file is provided
if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <input.xlsx>"
    exit 1
fi

input_file="$1"

# Check if the file exists and has .xlsx extension
if [[ ! -f "$input_file" ]] || [[ "${input_file##*.}" != "xlsx" ]]; then
    echo "Error: File does not exist or is not an XLSX file."
    exit 1
fi

# Construct the output file name
output_file="${input_file%.xlsx}.csv"

# Convert XLSX to CSV using xlsx2csv
xlsx2csv "$input_file" "$output_file"

echo "Converted '$input_file' to '$output_file'"
