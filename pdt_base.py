'''
Plausible Deniabity Toolkit

Utility functions and classes.

Copyright 2018-2022 amateur80lvl
License: BSD, see LICENSE for details.
'''

import json
import os
import shlex
import subprocess
import sys
import time
import traceback
from  types import SimpleNamespace

def read_config(base_dir):
    '''
    Read `config.json` file located in `base_dir`.
    '''
    config_filename = os.path.join(base_dir, 'config.json')
    with open(config_filename, 'r') as f:
        config = json.load(f)
    return config

class Task:
    '''
    The base class for procedures.
    Instances of this class can be used as a local storage for
    data that might be required by teardown method.
    Global data can be stored in the `context`.
    '''
    def __init__(self, config, invoke, context):
        self.config = config
        self.invoke = invoke
        self.context = context

    def setup(self):
        pass

    def teardown(self):
        pass

def procedure(config, invoke, *tasks):
    '''
    Run setup and teardown methods of tasks.
    '''
    sequence = setup(config, invoke, *tasks)
    teardown(sequence)

def setup(config, invoke, *tasks):
    '''
    Instantiate sequence classes, run setup functions.
    On success return the list of instantiated classes to run teardown methods.
    '''
    # Create container for global context
    context = SimpleNamespace()

    sequence = []
    try:
        for task_class in tasks:
            task = task_class(config, invoke, context)
            task.setup()
            sequence.append(task)
    except:
        teardown(sequence)
        raise
    return sequence

def teardown(sequence):
    '''
    Run teardown functions.
    '''
    for task in sequence[::-1]:
        try:
            task.teardown()
        except:
            print(traceback.format_exc())
            raise

class Invoke:
    '''
    Functions that use shell commands, either local, or remote via SSH.
    '''
    def __init__(self, remote=None, ssh_key=None):
        self.remote = remote
        self.ssh_key = ssh_key

    def run(self, command, check=True, shell=False, capture_output=True, **kwargs):
        print('>>>', command)
        if self.remote:
            args = ['ssh']
            if self.ssh_key:
                args.extend(['-i', self.ssh_key])
            args.append(f'root@{self.remote}')
            args.extend(shlex.split(command))
            shell = False
        else:
            if shell:
                args = command
            else:
                args = shlex.split(command)
        result = subprocess.run(args, capture_output=capture_output, text=True, shell=shell, **kwargs)
        if check and result.returncode != 0:
            raise Exception(f'Failed {command}: {result.stderr or result.stdout}')
        return result

    def set_devices(self, config):
        '''
        Devices in the configuration are identified by manufacturer serial number,
        here we set system device names throughout the configuration.
        '''
        result = self.run('lsblk -d -o NAME,SERIAL -J')
        devices = json.loads(result.stdout)
        device_map = dict()
        for device in devices['blockdevices']:
            serial = device['serial']
            if serial in config['devices']:
                tag = config['devices'][serial]
                device_map[tag] = f"/dev/{device['name']}"
        # check
        for path in device_map.values():
            if not self.path_exists(path):
                raise Exception(f'Internal error: device {path} does not exist.')
        # update config
        for volume_config in list(config['volumes'].values()):
            for k, v in list(volume_config.items()):
                if k == 'device' and isinstance(v, str):
                    tag = volume_config[k]
                    if tag not in device_map:
                       raise Exception(f'Device {tag} is not defined in the configuration')
                    volume_config['filename'] = device_map[tag]

    def path_exists(self, path):
        result = self.run(f'[ -e {path} ]', check=False)
        return result.returncode == 0

    def is_dir(self, path):
        result = self.run(f'[ -d {path} ]', check=False)
        return result.returncode == 0

    def get_root_device(self):
        '''
        Find device for the root file system.
        '''
        result = self.run('df')
        lines = result.stdout.splitlines()[1:]
        for line in lines:
            device, size, used, avail, percentage, mount_point = line.strip().split()
            if mount_point == '/':
                if device != '/dev/root':
                    return device
                kcmdline = self.run('cat /proc/cmdline').stdout
                root = re.search('root=(.+?)(\\s|$)', kcmdline).group(1)
                root = root.split('=', 1)[-1]
                for line in self.run('blkid').stdout.splitlines():
                    if root in line:
                        return line.split(':', 1)[0]
        raise Exception('Unable to find root device')

    def is_encrypted_volume_active(self, volume_name):
        result = self.run(f'cryptsetup status {volume_name}', check=False)
        return 'inactive' not in result.stdout and 'cipher' in result.stdout

    def get_encrypted_volume_device(self, volume_name):
        '''
        Get underlying device.
        '''
        result = self.run(f'cryptsetup status {volume_name}', check=False)
        for line in result.stdout.splitlines():
            line = line.strip()
            if line.startswith('device:'):
                return line[len('device:'):].strip()
        return None

    def losetup(self, device, offset, sizelimit, sector_size):
        '''
        Run losetup and return device name
        '''
        result = self.run(f'losetup -f {shlex.quote(device)} --offset {offset} --sizelimit {sizelimit}'\
                          f' --sector-size {sector_size} --show')
        return result.stdout.strip()

    def locrypt_open(self, volume_name, volume_config):
        '''
        Create loop device and open encrypted volume.
        '''
        offset = volume_config['start']
        if isinstance(offset, str):
            offset = eval(offset)
        if 'sizelimit' in volume_config:
            sizelimit = volume_config['sizelimit']
            if isinstance(sizelimit, str):
                sizelimit = eval(sizelimit)
        elif 'end' in volume_config:
            if isinstance(volume_config['end'], str):
                sizelimit = eval(volume_config['end']) - offset
            else:
                sizelimit = volume_config['end'] - offset
        else:
            raise Exception(f'Neither `end` nor `sizelimit` is specified in volume configuration for {volume_name}')

        loop_device = self.losetup(
            volume_config['filename'],
            offset,
            sizelimit,
            volume_config['sector_size']
        )
        print(f'Created loop device: {loop_device}')
        try:
            self.run(f'cryptsetup open {loop_device} {volume_name} --type plain --key-file -', input=volume_config['key'])
            volume_device = os.path.join('/dev/mapper', volume_name)
            print(f'Opened encrypted volume {volume_name}')
            return loop_device, volume_device
        except:
            self.run(f'losetup -d {loop_device}')
            print(f'Deleted loop device: {loop_device}')
            raise

    def locrypt_close(self, volume_name, loop_device):
        '''
        Close encrypted volume and delete loop device.
        '''
        attempt = 0
        while True:
            attempt += 1
            result = self.run(f'cryptsetup close {volume_name}', check=False)
            if result.returncode != 0:
                if attempt > 1:
                    time.sleep(1)
                print(f'  {volume_name} is busy, trying again')
                continue
            time.sleep(1)
            for i in range(10):
                if not self.is_encrypted_volume_active(volume_name):
                    print(f'Closed encrypted volume {volume_name}')
                    self.run(f'losetup -d {loop_device}')
                    print(f'Deleted loop device: {loop_device}')
                    return
                time.sleep(0.5)
            print(f'Another attempt to close encrypted volume {volume_name}')

    def locrypt_unmount(self, directory):
        '''
        Check the directory is an encrypted volume and do locrypt_close.
        '''
        directory = directory.rstrip('/')
        lines = self.run('df').stdout.splitlines()[1:]
        for line in lines:
            device, size, used, avail, percentage, mount_point = line.strip().split()
            if mount_point == directory:
                for line in self.run(f'cryptsetup status {device}').stdout.splitlines():
                    line = line.strip().split()
                    if line[0] == 'device:' and line[1].startswith('/dev/loop'):
                        loop_device = line[1]
                        self.unmount(directory)
                        self.locrypt_close(device, loop_device)
                        return
                raise Exception(f'{device} does not look like an encrypted volume')
        raise Exception(f'{directory} does not look like a mounted volume')

    def unmount(self, directory):
        while True:
            self.kill_lsof_processes(directory)
            try:
                self.run(f'umount {directory}')
                break
            except:
                print(f'Trying to unmount {directory}')
                time.sleep(1)
        print(f'Unmounted {directory}')

    def is_formatted(self, device):
        '''
        Check if a device is formatted.
        '''
        result = self.run('blkid')
        lines = result.stdout.splitlines()
        devices = [dev for dev, _ in (line.split(':', 1) for line in lines)]
        return device in devices

    def kill_user_processes(self, username):
        '''
        Kill all processes owned by user.
        '''
        while True:
            result = self.run(f'ps --user {username}', check=False)
            lines = result.stdout.splitlines()[1:]
            pids = ' '.join(pid for pid, _ in (line.strip().split(' ', 1) for line in lines))
            if pids:
                self.run(f'kill -9 {pids}', check=False)
                time.sleep(1)
            else:
                break

    def kill_lsof_processes(self, directory):
        '''
        Kill all processes that listed in lsof output for the directory.
        '''
        result = self.run(f'lsof {directory}', check=False)
        lines = result.stdout.splitlines()[1:]
        pids = ' '.join(pid for _, pid in (line.strip().split(' ', 1) for line in lines))
        if pids:
            self.run(f'kill -9 {pids}', check=False)
