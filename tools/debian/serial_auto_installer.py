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
If the install hangs after printing
> Interrupting autoboot
there is most likely something wrong with the state of the serial port on the installbone
"""


import serial
import sys
import time

from pexpect import fdpexpect


class LOGGER(object):
    @staticmethod
    def log(line):
        sys.stdout.write('{0}\n'.format(line))
        sys.stdout.flush()


if len(sys.argv) != 2:
    print("Usage exmaple: python serial_auto_installer.py /dev/ttyUSB0")
    sys.exit(0)

serial_device = sys.argv[1]

class install(object):
    """
    Contains the methods to install the gateway
    """
    @staticmethod
    def rock():
        """
        Installs your gateway
        :return: boolean
        """
        try:
            installer.expect('Press SPACE to abort autoboot in 2 seconds', timeout=120)
            LOGGER.log("> Interrupting autoboot")
            installer.send(' ')
            installer.expect('=> ')
            LOGGER.log("> Searching for device tree files")
            installer.sendline('run findfdt')
            installer.expect('=> ')
            LOGGER.log("> Updating nfs boot options ...")
            installer.sendline('setenv nfsopts "v3,nolock"')
            installer.expect('=> ')
            LOGGER.log("> Booting from the network ...")
            installer.sendline('run netboot')
            LOGGER.log("> Waiting for Login ...")
            installer.expect('nfsroot login: ', timeout=60)
            installer.sendline('root')
            installer.expect('Password: ')
            installer.sendline('bbb')
            installer.expect('root@nfsroot:~# ')
            installer.sendline('/opt/install/init-eMMC-flasher-v3-nfs.sh')
            return True
        except:
            return False

    @staticmethod
    def roll():
        """
        Check if the gateway is installed, rebooted and runs OK
        Also gives you the possibility to interact with it.
        :return: boolean
        """
        try:
            installer.send("\n")
            installer.expect('OpenMotics login: ', timeout=2)
            feedback = installer.before.decode().splitlines()[-4:]
            LOGGER.log("\n***********************************************************\n{}***********************************************************".format('\n'.join(feedback)))
            #interact = input("Go interactive (y|n): ") or n
            #if interact == 'y':
            #    installer.interact()
            return True
        except:
            return False

if __name__ == '__main__':
    ready = 'n'
    while True:
        while ready == 'n':
            LOGGER.log("""Procedure to install a new gateway:
INSTALLBONE
   1. Connect USB-Ethernet(eth1) port to the PUBLIC NETWORK
   2. Connect Ethernet(eth0) to your INSTALL NETWORK(direct or switch)

NEW GATEWAY
   1. Leave the gateway powered off
   2. Connect Ethernet(eth0) to INSTALL NETWORK 
   3. Connect Installbone serial port cable to the gateway serial console.
""")
            try:
                ready = input("All set? (y|n|e): ") or 'n'
            except ValueError:
                LOGGER.log('Invalid input, try again')
                ready = 'n'
            if ready == 'e':
                sys.exit(0)

        ser = serial.Serial(serial_device, 115200)
        installer = fdpexpect.fdspawn(ser)

        action = 0
        while action == 0:
            LOGGER.log("""\nAvailable actions:
   1. Install new gateway
   2. Check installed gateway
   3. Exit the installer
""")
            try:
                action = int(input("Choice: "))
            except ValueError:
                LOGGER.log("! Invalid input, try again !")
                action = 0

            if action == 1:
                LOGGER.log("\nPower on the gateway now\n")
                installing = install.rock()
                if installing:
                    LOGGER.log("> Get a Coffee ... or proceed on to your next gateway")
                    time.sleep(10)
                else:
                    LOGGER.log("Oops ... something went wrong, you might want to give it another shot")
            elif action == 2:
                installed = install.roll()
                if installed:
                    LOGGER.log('<< GREEN STICKER TIME >>')
                else:
                    LOGGER.log('If this is the first time you check within 5mins after starting the installation,'
                               'then come back later and check again, it is most likely still rocking.\n'
                               'In the other case something might have gone wrong')
                    action = 0
            elif action == 3:
                sys.exit(0)

installer.pexpect('root@OpenMotics:/# ')