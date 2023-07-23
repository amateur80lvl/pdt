'''
Plausible Deniabity Toolkit

Emergency switch. Just an example. Modify for your needs.

If you don't want anyone to look at your work in progress...
switch to a predefined virtual terminal by pressing some key
on your tablet.

Tap three times to shutdown your system.

Copyright 2022 amateur80lvl
License: BSD, see LICENSE for details.
'''

tablet = '/dev/input/by-id/usb-UGTABLET_DECO_01-event-kbd'
keyboard = '/dev/input/by-path/platform-i8042-serio-0-event-kbd'
touchpad = '/dev/input/by-path/platform-i8042-serio-4-event-mouse'
tablet_key_code = 57  # lowest key (?)
kb_key_code = 125     # windows key
min_tap_interval = 0.12
max_tap_interval = 0.25

emergency_terminal = 7

import asyncio

import evdev

async def main():
    await asyncio.gather(
        asyncio.create_task(keycode_checker(tablet, tablet_key_code)),
        asyncio.create_task(keycode_checker(keyboard, kb_key_code)),
        asyncio.create_task(touchpad_checker(touchpad))
    )

async def keycode_checker(input_device, key_code):
    while True:
        try:
            dev = evdev.InputDevice(input_device)
        except Exception:
            await asyncio.sleep(1)
            continue

        try:
            packet = []
            async for ev in dev.async_read_loop():
                ev = evdev.categorize(ev)
                if isinstance(ev, evdev.SynEvent):
                    await process_event(packet, key_code)
                    packet = []
                else:
                    packet.append(ev)
        except Exception:
            await asyncio.sleep(1)
            continue

async def process_event(packet, key_code):
    for ev in packet:
        if isinstance(ev, evdev.KeyEvent) \
           and ev.scancode == key_code \
           and ev.keystate == evdev.KeyEvent.key_down:
            await switch_terminal()
            return

async def switch_terminal():
    proc = await asyncio.create_subprocess_exec('chvt', str(emergency_terminal))
    await proc.communicate()

async def touchpad_checker(input_device):
    while True:
        try:
            dev = evdev.InputDevice(input_device)
        except Exception:
            await asyncio.sleep(1)
            continue

        try:
            packet = []
            async for ev in dev.async_read_loop():
                ev = evdev.categorize(ev)
                if isinstance(ev, evdev.SynEvent):
                    await process_touchpad_event(packet)
                    packet = []
                else:
                    packet.append(ev)
        except Exception as e:
            print(e)
            await asyncio.sleep(1)
            continue

touch_window = []

async def process_touchpad_event(packet):
    global touch_window
    for ev in packet:
        if isinstance(ev, evdev.KeyEvent) \
           and ev.scancode == evdev.ecodes.BTN_TOOL_FINGER \
           and ev.keystate == evdev.KeyEvent.key_down:
            touch_window.append(ev.event.timestamp())
            if len(touch_window) >= 3:
                if len(touch_window) > 3:
                    del(touch_window[0])
                t1 = touch_window[1] - touch_window[0]
                t2 = touch_window[2] - touch_window[1]
                if min_tap_interval < t1 and t1 < max_tap_interval and \
                   min_tap_interval < t2 and t2 < max_tap_interval:
                    print('SHUTDOWN')
                    proc = await asyncio.create_subprocess_shell('shutdown -r now')
                    await proc.communicate()

asyncio.run(main())
