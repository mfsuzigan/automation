#!/bin/bash

## Random image slideshow script
## 1. reads directory passed as first argument
## 2. randomly picks JPG, PNG or WEBP file and sets it as the background image
## 3. sleeps for n seconds passed as second argument and repeats

image_dir=$1
sleep_in_seconds=$2
file_count_in_folder=$(find . -maxdepth 1 -type f -regex ".*\.[(jJpP(eE)+gG)|(pPnNgG)|(wWeEbB)]+$" | wc -l)

while [ 1 == 1 ]; do
  random_file_index=$(( $RANDOM%${file_count_in_folder}+1 ))
  counter=1

  for file in "${image_dir}"/*; do

    if [[ ${counter} == ${random_file_index} ]]; then
      echo "Setting background: ${file}"
      gsettings set org.gnome.desktop.background picture-uri $file
      break
    fi

    let counter++
  done

  sleep $sleep_in_seconds

done