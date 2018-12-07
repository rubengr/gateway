#!/usr/bin/python

import os
import sys
import shutil
import re
import subprocess

import urllib2

#import crypt
#import random
#import string

#from ConfigParser import ConfigParser

#tmp_path = '/opt/writer/tmp/'
#root_path = '/opt/writer/mnt/root/'
#opt_path = '/opt/writer/mnt/opt/'
rootfs_path = '/export/rootfs'
client_path = '/export/rootfs/opt/clients'
host = "dev.openmotics.com"
token = "f2b96488-a563-4613-a098-1b7f78f9f2b7"
mac = sys.argv[1]


def do_action(installtype, action, args):
    url = "https://{0}/portal/{1}_install/?token={2}&action={3}".format(host, installtype, token, action)
    for (key, value) in args.iteritems():
        url += "&%s=%s" % (key, value)
    return url

    return urllib2.urlopen(url).read()


def copy_files(src_path, src_files, dst_path):
    if not os.path.exists(dst_path):
        os.makedirs(dst_path)

    for src in src_files:
        shutil.copy(src_path + src, dst_path)

# Exit if mac address is invalid
valid_mac = re.search(r'([0-9A-F]{2}[:]){5}([0-9A-F]{2})', mac, re.I)
if not valid_mac:
    sys.exit(1)

client_installation_path = '{0}/{1}/'.format(client_path, mac.replace(':', ''))
client_configuration = '{0}{1}'.format(client_installation_path, 'client.tgz')
if os.path.exists(client_configuration):
    sys.exit(0)

## Queue a new gateway for install
#success = do_action("admin", "get", {"queue_batch" : 1})

## Get the installation to install
installation_id = do_action("gateway", "get", {})
print "Installing installation %s" % installation_id

## Download the installation files
download_response = do_action("gateway", "download", {"installation_id": installation_id})

if not os.path.exists(client_installation_path):
    os.makedirs(client_installation_path)

client_file = open(client_configuration, 'w')
client_file.write(download_response)
client_file.close()




