#!/bin/sh
pwd

login=`curl -sk -X GET "https://localhost:8089/login?username=openmotics&password=123456"`
token=`echo $login | grep -Po '"token": "\K\w+'`

wget --no-check-certificate --header="Authorization: Bearer $token" -O initial.xml https://localhost:8089/plugins/testrunner/get_test_report
echo "got test report"
csplit -f gateway -b "%04d.xml" initial.xml '/^<?xml version="1.0" ?>$/' '{*}'
find . -type f -empty -delete
