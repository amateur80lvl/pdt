'''
Plausible Deniabity Toolkit

Collect and compare sector hashes.

Copyright 2018-2022 amateur80lvl
License: BSD, see LICENSE for details.
'''

from hashlib import blake2s
import sys

digest_size = 8  # This is quite sufficient size IMAO. No collisions for 120GB SSD.

def parse_args():
    if len(sys.argv) < 4:
        print('Arguments: command device filename [start-lba end-lba] [sector-size] [min-length]]')
        sys.exit(1)
    args = {
        'command': sys.argv[1],
        'device_filename': sys.argv[2],
        'hashes_filename': sys.argv[3],
        'start_lba': None,
        'end_lba': None,
        'sector_size': 512,
        'min_length': 1
    }
    argv = sys.argv[4:]
    if len(argv) >= 2:
        args['start_lba'] = int(argv.pop(0))
        args['end_lba'] = int(argv.pop(0))
        assert args['start_lba'] <= args['end_lba']

    if len(argv) >= 1:
        args['sector_size'] = int(argv.pop(0))
        assert args['sector_size'] in [512, 1024, 2048, 4096, 8192]

    if len(argv) >= 1:
        args['min_length'] = int(argv.pop(0))

    return args

def compute_hashes(device_filename, hashes_filename, sector_size):
    with open(hashes_filename, 'wb') as f_hashes:
        with open(device_filename, 'rb') as f_dev:
            while True:
                data = f_dev.read(sector_size)
                if len(data) != sector_size:
                    break
                h = blake2s(data, digest_size=digest_size)
                _ = f_hashes.write(h.digest())

def find_intact_regions(device_filename, start_lba, end_lba, hashes_filename, sector_size, min_length):
    lba = 0
    with open(hashes_filename, 'rb') as f_hashes:
        if start_lba:
            f_hashes.seek(start_lba * digest_size)
        with open(device_filename, 'rb') as f_dev:
            if start_lba:
                f_dev.seek(start_lba * sector_size)
                lba = start_lba
            intact_region_start = lba
            intact_region_end = lba
            while True:
                if end_lba and lba > end_lba:
                    break
                data = f_dev.read(sector_size)
                if len(data) != sector_size:
                    break
                h_orig = f_hashes.read(digest_size)
                lba += 1
                h = blake2s(data, digest_size=digest_size)
                if h_orig == h.digest():
                    intact_region_end += 1
                else:
                    region_length = intact_region_end - intact_region_start
                    if region_length >= min_length:
                        print('%s\t%s-%s' % (region_length, intact_region_start, intact_region_end))
                    intact_region_start = lba
                    intact_region_end = lba
            region_length = intact_region_end - intact_region_start
            if region_length >= min_length:
                print('%s\t%s-%s' % (region_length, intact_region_start, intact_region_end))

if __name__ == '__main__':
    args = parse_args()
    if args['command'] == 'compute':
        compute_hashes(args['device_filename'], args['hashes_filename'], args['sector_size'])
    elif args['command'] == 'find-intact':
        find_intact_regions(args['device_filename'], args['start_lba'], args['end_lba'],
                            args['hashes_filename'], args['sector_size'], args['min_length'])
    else:
        print('bad command:', args['command'])
