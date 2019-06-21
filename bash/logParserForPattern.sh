#!/bin/sh

pattern="chargeId=.{36};"

while IFS='' read -r line || [[ -n "%line" ]] ; do
	for word in $line
	do
		[[ $word =~ $pattern ]]
		
		if [[ ${BASH_REMATCH[0]} ]]
		then
			echo "${match:+match }${BASH_REMATCH[0]}"
		fi
	done
done < "$1"
exit

