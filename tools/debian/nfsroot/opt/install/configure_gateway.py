# Copyright (C) 2016 OpenMotics BVBA
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
#
# Extract client config
# Set password
#
#
#
# Add Registration key to /etc/issue
#
"""

import os
import sys
import shutil
import subprocess

import urllib2

import crypt
import random
import string

from ConfigParser import ConfigParser

root_path = "/tmp/rootfs/"
opt_path = "/tmp/rootfs/opt/"
clients_path = "/opt/clients"
hostname = "OpenMotics"

def copy_files(src_path, src_files, dst_path):
    if not os.path.exists(dst_path):
        os.makedirs(dst_path)

    for src in src_files:
        shutil.copy(src_path + src, dst_path)

def get_local_mac_address(interface='eth0'):
    """ Get the local ip address. """
    try:
        lines = subprocess.check_output("ifconfig {}".format(interface), shell=True)
        return lines.split("\n")[3].strip().split(" ")[1]
    except Exception:
        return None
## Install the client files
#do_action("install", { "installation_id" : installation_id })

mac = get_local_mac_address().replace(":","")
tmp_path = "/tmp/{0}/".format(mac)
if not os.path.isdir(tmp_path):
    os.makedirs(tmp_path)

subprocess.call([ "/bin/tar", "xzf", "{0}/{1}/{2}".format(clients_path,mac,'client.tgz')], cwd=tmp_path)

copy_files(tmp_path + "client/", [ "vpn.conf", "ca.crt", "ta.key", "client.crt", "client.key" ], root_path + "etc/openvpn/client")
copy_files(tmp_path + "client/", [ "openmotics.conf", "https.crt", "https.key" ], opt_path + "openmotics/etc/")

os.rename("{0}/{1}/{2}".format(root_path, "etc/openvpn/client", "vpn.conf"), "{0}/{1}/{2}".format(root_path, "etc/openvpn/client", "omcloud.conf"))

## Set the root password
config = ConfigParser()
config.read(tmp_path + "client/openmotics.conf")
regkey = config.get('OpenMotics', 'uuid')
password = config.get('OpenMotics', 'cloud_pass')

salt = ''.join(random.choice(string.ascii_lowercase + string.ascii_uppercase + string.digits) for _ in range(2))
hashed_password = crypt.crypt(password, salt)
subprocess.call([ "chroot", root_path, "/usr/sbin/usermod", "-p", hashed_password, "root" ])

# Change some systemd config and service files
copy_files("/opt/install/files/", ["journald.conf"], "{0}etc/systemd".format(root_path))
copy_files("/opt/install/files/", ["supervisor.service"], "{0}lib/systemd/system".format(root_path))
copy_files("/opt/install/files/", ["openmotics-gpios.service",], "{0}lib/systemd/system/".format(root_path))

# Set the hostname
os.chroot(root_path)
subprocess.call(["sed", "-i", "s/nfsroot/OpenMotics/g", "/etc/hostname"])
subprocess.call(["sed", "-i", "s/nfsroot/OpenMotics/g", "/etc/hosts"])

# Set our regkey as machine_id
machine_id = regkey.replace("-", "")
for file in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
    with open(file, "w") as mid:
        mid.write("{}\n".format(machine_id))

# Update cmdline to enable watchdog early in the boot process
subprocess.call(["sed", "-i", "/^cmdline.*/s/$/ omap_wdt.early_enable=1/", "/boot/uEnv.txt"])

# Clean directories
dirs_to_remove = [tmp_path, ]
for dir in dirs_to_remove:
    if os.path.isdir(dir):
        shutil.rmtree(dir)

# Readonly rootfs changes
# Relocate tmp dirs to /run required for readonly rootfs
dirs_to_link = {'/var/tmp': '/tmp',
                '/var/log': '/run/log'}
for current, target in dirs_to_link.iteritems():
    if os.path.islink(current):
        os.remove(current)
    elif os.path.isdir(current):
        shutil.rmtree(current)
    os.symlink(target, current)

# Move root home directory to /opt/root
subprocess.call(["usermod", "-d", "/opt/root", "-m", "root"])

# Enable/Disable services
# System services
os.chdir('/etc/systemd/system/multi-user.target.wants')
if not os.path.exists('connman.service'):
    os.symlink('/lib/systemd/system/connman.service', 'connman.service')
if not os.path.exists('supervisor.service'):
    os.symlink('/lib/systemd/system/supervisor.service', 'supervisor.service')
if not os.path.exists('openmotics-gpios.service'):
    os.symlink('/lib/systemd/system/openmotics-gpios.service', 'openmotics-gpios.service')
os.remove('bb-wl18xx-wlan0.service')
os.remove('generic-board-startup.service')
# Removed in the image
#os.chdir('/etc/systemd/system/timers.target.wants')
#os.remove('apt-daily.timer')
#os.remove('apt-daily-upgrade.timer')

# Enable DHCP on network interface
#os.subprocess.call(["/usr/bin/connmanctl",])

# Add registration key to Login message
with open('/etc/motd', 'w') as msg:
    msg.write("""
  ______                                 __       __              __      __                     
 /      \                               /  \     /  |            /  |    /  |                    
/OOOOOO  |  ______    ______   _______  MM  \   /MM |  ______   _tt |_   ii/   _______   _______ 
OO |  OO | /      \  /      \ /       \ MMM  \ /MMM | /      \ / tt   |  /  | /       | /       |
OO |  OO |/pppppp  |/eeeeee  |nnnnnnn  |MMMM  /MMMM |/oooooo  |tttttt/   ii |/ccccccc/ /sssssss/ 
OO |  OO |pp |  pp |ee    ee |nn |  nn |MM MM MM/MM |oo |  oo |  tt | __ ii |cc |      ss      \  
OO \__OO |pp |__pp |eeeeeeee/ nn |  nn |MM |MMM/ MM |oo \__oo |  tt |/  |ii |cc \_____  ssssss  |
OO    OO/ pp    pp/ ee       |nn |  nn |MM | M/  MM |oo    oo/   tt  tt/ ii |cc       |/     ss/ 
 OOOOOO/  ppppppp/   eeeeeee/ nn/   nn/ MM/      MM/  oooooo/     tttt/  ii/  ccccccc/ sssssss/  
          pp |                                                                                         
          pp |                                                                                         
          pp/                                                                                          

""")

with open('/etc/issue', 'w') as msg:
    msg.write("\nWelcome to the OpenMotics Gateway\n")
    msg.write("\nYour registration key: {}\n\n".format(regkey))


# Delete the default "debian" user
subprocess.call(["/usr/sbin/userdel", "-r", "debian"])


## Tell the API we are ready
#do_action("ready", { "installation_id" : installation_id })
