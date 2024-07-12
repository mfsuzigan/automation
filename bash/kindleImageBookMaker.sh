#!/bin/bash

bookname="$1"
mkdir -p $bookname
echo "<html><head><title>$bookname</title></head><body><h1>$bookname</h1>" > "$bookname/index.html"
img_dir="$2"


for imageFile in "${img_dir}"/*.{jpg,png,jpeg,gif}; do
	cp "$imageFile" $bookname
	echo "<img src=\"${imageFile##*/}\"/>" >> "$bookname/index.html"
done


echo "</body></html>" >> "$bookname/index.html"
ebook-convert "$bookname/index.html" "/media/michel/Kindle/documents/$1.mobi"
rm -r $bookname
#ebook-convert "$bookname/index.html" $1.mobi
