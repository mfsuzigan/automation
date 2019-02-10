#!/bin/bash
# Renomeacao em massa de arquivos
# Usa a variavel IFS (internal field separator) para quebrar nomes de arquivos em arrays e renomea-los

IFS='_'

for imageName in IMG*.jpg; do
	#mv $x test/${x%.png}test.png;
	imageNameSplit=($imageName)
	newImageName="${imageNameSplit[1]}.jpg"
	echo "from $imageName to $newImageName"
	mv "$imageName" "$newImageName"
done

unset IFS
