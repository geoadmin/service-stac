#!/bin/bash
# This script updates the Pipfile automatically. It will update all version strings of type
# "~=x.x.x" to their respective latest version. Version strings of dependencies that use other
# version specifiers (like "*") will be left untouched. All dependencies will be updated
# (with "pipenv update") in the process.
# A regex can be optionally specified as first argument. In this case, only the version strings
# of packages matching the regex will be updated. (e.g. update_to_latest.sh 'django.*')
# This script is meant as a helper only. Use git to revert unwanted changes made by this script.

cd "$(dirname "$0")" || exit
#If an argument was passed to the script, it will be used as a regular expression
#Else we will simply match any package name
regexp=${1:-'\S+'}
line_regexp="^($regexp) = \"~=[0-9\\.]+\"(.*)$"

#Generate an array of all packages that need to be updated and switch their version to "*"
packages_to_modify=( $(cat Pipfile | sed -En "s/$line_regexp/\1/ip") )
echo "The script will try to update the following packages: ${packages_to_modify[*]}"
read -p "Do you want to contnue? [Y|N] " -n 1 -r
echo
[[ ! $REPLY =~ ^[Yy]$ ]] && exit
sed -Ei "s/$line_regexp/\1 = \"*\"\2/i" Pipfile

# Update the packages to the latest version
pipenv update --dev

# Set the current version in the Pipfile (only for the packages that were updated)
updateVersions=""
while read -r name version ; do
    if [[ " ${packages_to_modify[*]} " == *" $name "*  ]] ; then
        updateVersions+="/^$name =/s/\"\\*\"/$version/"
        updateVersions+=$'\n'
    fi
done < <(pipenv run pip freeze | sed -E 's/==([0-9\.]+\w*)/ "~=\1"/')
sed -Ei -f <(echo "$updateVersions") Pipfile
