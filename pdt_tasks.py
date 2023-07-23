'''
Plausible Deniabity Toolkit

Basic tasks.

Copyright 2018-2022 amateur80lvl
License: BSD, see LICENSE for details.
'''

import traceback
from pdt_base import Task

class CheckCommands(Task):

    commands = '''
        blkid
        cryptsetup
        df
        ip
        kill
        losetup
        lsblk
        lsof
        mkdir
        mkfs
        mount
        ps
        rsync
        shutdown
        systemctl
        umount
    '''.split()

    def setup(self):
        for cmd in self.commands:
            self.invoke.run(f'which {cmd}')


class MountRoot(Task):

    def setup(self):
        self.root_device = self.invoke.get_root_device()
        print(f'Mounting root partition {self.root_device} to /mnt/root')
        self.invoke.run(f'mkdir -p /mnt/root')
        self.invoke.run(f'mount {self.root_device} /mnt/root')

    def teardown(self):
        self.invoke.run('umount /mnt/root')
        print(f'Unmounted {self.root_device} from /mnt/root')


def TmpfsMounts(*mount_points):
    '''
    Mount tmpfs to specific `mount_points`.
    '''
    class TmpfsMounts(Task):

        def setup(self):
            self.mounted_tmpfs = []
            try:
                for directory in mount_points:
                    self.invoke.run(f'mkdir -p {directory}')
                    self.invoke.run(f'mount -t tmpfs -o size=64K tmpfs {directory}')
                    print(f'Mounted tmpfs on {directory}')
                    self.mounted_tmpfs.append(directory)
            except:
                self.teardown()
                raise

        def teardown(self):
            for directory in self.mounted_tmpfs[::-1]:
                try:
                    self.invoke.run(f'umount {directory}')
                    print(f'Unmounted tmpfs {directory}')
                except:
                    print(traceback.format_exc())
            self.mounted_tmpfs = []

    return TmpfsMounts


def BindMounts(*mount_spec):
    '''
    Mount with --bind option.
    '''
    class BindMounts(Task):

        def setup(self):
            self.mounts = []
            try:
                for src, dest in mount_spec:
                    if not self.invoke.path_exists(dest):
                        if self.invoke.is_dir(src):
                            self.invoke.run(f'mkdir -p {dest}')
                        else:
                            self.invoke.run(f'touch {dest}')
                    self.invoke.run(f'mount --bind {src} {dest}')
                    print(f'Bound {src} to {dest}')
                    self.mounts.append(dest)
            except:
                self.teardown()
                raise

        def teardown(self):
            for directory in self.mounts[::-1]:
                try:
                    self.invoke.run(f'umount {directory}')
                    print(f'Unbound {directory}')
                except:
                    print(traceback.format_exc())
            self.mounts = []

    return BindMounts


def OverlayMounts(*mount_spec):
    '''
    Mount overlay filesystems.
    '''
    class OverlayMounts(Task):

        def setup(self):
            self.mounts = []
            try:
                for lower, upper, work, dest in mount_spec:
                    if not self.invoke.path_exists(dest):
                        if self.invoke.is_dir(src):
                            self.invoke.run(f'mkdir -p {dest}')
                        else:
                            self.invoke.run(f'touch {dest}')
                    self.invoke.run(f'mount -t overlay overlay -o relatime,lowerdir={lower},upperdir={upper},workdir={work} {dest}')
                    print(f'Mounted {lower}+{upper} to {dest}')
                    self.mounts.append(dest)
            except:
                self.teardown()
                raise

        def teardown(self):
            for directory in self.mounts[::-1]:
                try:
                    self.invoke.run(f'umount {directory}')
                    print(f'Unbound {directory}')
                except:
                    print(traceback.format_exc())
            self.mounts = []

    return OverlayMounts


class MountVolumes(Task):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.opened_volumes = []
        self.mounted_volumes = []
        self.mounts = self.invoke.run('cat /proc/mounts').stdout

    def setup(self):
        try:
            for volume_name, volume_config in self.config['volumes'].items():
                volume_device = f'/dev/mapper/{volume_name}'
                if f'{volume_device} {volume_config["mount_point"]}' in self.mounts:
                    print(f'Skipping already mounted {volume_name}')
                    continue

                if not self.invoke.path_exists(volume_config['mount_point']):
                    self.invoke.run(f'mkdir {volume_config["mount_point"]}')

                loop_device = self.invoke.get_encrypted_volume_device(volume_name)
                if loop_device:
                    print(f'Already opened {volume_name}')
                else:
                    print(f'Opening {volume_name}')
                    loop_device, volume_device = self.invoke.locrypt_open(volume_name, volume_config)
                    # check if opened okay
                    try:
                        if not self.invoke.is_encrypted_volume_active(volume_name):
                            raise Exception(f'Failed opening {volume_name}')
                    except:
                        self.invoke.locrypt_close(volume_name, loop_device)
                        raise

                # check if formatted
                try:
                    if not self.invoke.is_formatted(volume_device):
                        self.invoke.locrypt_close(loop_device, volume_name)
                        raise(f'Not formatted {volume_device}')
                    # good, add to the teardown list
                    self.opened_volumes.append((loop_device, volume_name))
                except:
                    self.invoke.locrypt_close(volume_name, loop_device)
                    raise

                print(f'Mounting {volume_device}')
                mount_options = ','.join(set(['relatime'] + volume_config.get('mount_options', [])))
                self.invoke.run(f'mount -o {mount_options} {volume_device} {volume_config["mount_point"]}')
                self.mounted_volumes.append(volume_config['mount_point'])
        except:
            self.teardown()
            raise

    def teardown(self):
        # XXX exception  handling?
        for mount_point in self.mounted_volumes:
            self.invoke.run(f'umount {mount_point}')
        for loop_device, volume_name in self.opened_volumes:
            self.invoke.locrypt_close(volume_name, loop_device)
        self.mounted_volumes = []
        self.opened_volumes = []


def RestartServices(*setup, teardown=None):

    class RestartServices(Task):

        def setup(self):
            self.restart_services(setup)

        def teardown(self):
            self.restart_services(teardown or [])

        def restart_services(self, services):
            self.invoke.run('systemctl daemon-reexec')
            self.invoke.run(f'systemctl restart {" ".join(services)}')

    return RestartServices


class TeardownReboot(Task):

    def teardown(self):
        input('Press ENTER for reboot: ')
        print('Restarting system')
        self.invoke.run('shutdown -r now')


class TeardownPressEnter(Task):

    def teardown(self):
        input('Press ENTER for teardown: ')


class TeardownOnSignal(Task):
    '''
    How to broadcast teardown signal:
        echo | nc -b -u -q 0 172.16.255.255 12356
    or
        echo | socat - UDP-DATAGRAM:172.16.255.255:12356,broadcast
    '''

    def teardown(self):
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.bind(('0.0.0.0', 12356))
        print('Waiting for teardown UDP packet')
        s.recv(512)
        print('Restarting system')
        self.invoke.run('shutdown -r now')
