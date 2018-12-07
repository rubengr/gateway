#!/bin/bash
set -x

op="${1:-op}"
mac="${2:-mac}"
ip="${3:-ip}"
hostname="${4}"

timestamp="`date '+%Y-%m-%d %H:%M:%S'`"
thirdoct=`echo $ip | awk '{split($0,i,"."); print i[3]}'`

if [ $thirdoct == 13 ];
then
   echo "Getting client files from Openmotics Cloud for $mac - $ip"
   /usr/bin/python /opt/install/get_client.py $mac
fi
