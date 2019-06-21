#!/bin/bash
# Reads text file containing links to webpages line by line and saves corresponding PDF using headless Chrome

input="links.txt"
count=0

while IFS= read -r line
do
	destination="/home/michelsuzigan/Documents/aws/pdfs/$count.pdf"
	echo "PDFing link $count: $line"
	sudo /opt/google/chrome/chrome --headless --print-to-pdf="$destination" $line --no-sandbox 
	sudo chown michelsuzigan "$destination"
	(( count++ ))
done < "$input"
echo "Done!"
