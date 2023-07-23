'''
Plausible Deniabity Toolkit

Filesystem-related tasks.

Copyright 2018-2022 amateur80lvl
License: BSD, see LICENSE for details.
'''

import traceback
from pdt_base import Task

class RemountMnt(Task):
    '''
    Re-mount /mnt directory to tmpfs.
    This is a quite specific task, which can be considered as an example.
    Modify for your needs.
    '''

    def setup(self):
        self.invoke.run('systemctl stop nfs-kernel-server')
        try:
            self.invoke.run('umount /mnt/filestore')
            try:
                self.invoke.run('mount -t tmpfs -o size=64K tmpfs /mnt')
                self.invoke.run('mkdir /mnt/filestore')
            finally:
                self.invoke.run('mount /dev/sda2 /mnt/filestore')
        finally:
            self.invoke.run('systemctl start nfs-kernel-server')
        print(f'Re-mounted tmpfs on /mnt')

    def teardown(self):
        self.invoke.run('systemctl stop nfs-kernel-server')
        try:
            self.invoke.run('umount /mnt/filestore')
            try:
                self.invoke.run('umount /mnt')
            finally:
                self.invoke.run('mount /dev/sda /mnt/filestore')
        finally:
            self.invoke.run('systemctl start nfs-kernel-server')
