#!/usr/bin/env python3
"""Display native A7M3 frames and send camera commands over the virtual UART."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import queue
import socket
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('native_capture', ROOT / 'scripts/capture-menu.py')
capture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(capture)


class Camera:
    def __init__(self, closing=None):
        self.closing = closing or threading.Event()
        self.directory = Path(tempfile.mkdtemp(prefix='a7m3-qemu-'))
        self.output = ROOT / 'output' / time.strftime('%Y%m%d-%H%M%S')
        self.output.mkdir(parents=True, exist_ok=False)
        self.endpoint = self.directory / 'qmp'
        self.frames = queue.Queue()
        self.process = subprocess.Popen([str(ROOT / 'start-a7m3-ui.sh'), '-qmp',
            f'unix:{self.endpoint},server=on,wait=off'], cwd=ROOT,
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            start_new_session=True)
        self.channel = None
        self.stream = None
        self.frame = 0
        self.reader = threading.Thread(target=self.read_log, daemon=True)
        self.reader.start()

    def read_log(self):
        meta, pages = None, []
        try:
            with (self.output / 'serial.log').open('wb') as log:
                for raw in self.process.stdout:
                    log.write(raw)
                    log.flush()
                    line = raw.decode('utf-8', errors='replace')
                    if line.lstrip().startswith('['):
                        continue
                    if (('input.' in line and '.error=' in line) or any(mark in line for mark in ('headless.error.', 'UNSUPPORTED', 'unsupported.prologue', 'not found (required by /usr/lib/libuiobserve.so)'))):
                        self.frames.put(RuntimeError(line.strip()))
                    for prefix in ('UI_CAPTURE_META ', 'UI_CAPTURE_PAGE ', 'UI_CAPTURE_READY '):
                        if prefix not in line:
                            continue
                        item = json.loads(line.split(prefix, 1)[1])
                        if prefix == 'UI_CAPTURE_META ':
                            meta, pages = item, []
                        elif prefix == 'UI_CAPTURE_PAGE ':
                            if len(pages) >= 151:
                                raise ValueError('too many native frame segments')
                            pages.append(item)
                        else:
                            self.frames.put((meta, pages, item))
                        break
            self.frames.put(RuntimeError(f'QEMU output closed; see {self.output / "serial.log"}'))
        except Exception as error:
            self.frames.put(error)

    def connect(self):
        if self.stream:
            return
        self.channel = socket.socket(socket.AF_UNIX)
        self.channel.settimeout(10)
        self.channel.connect(str(self.endpoint))
        self.stream = self.channel.makefile('rwb')
        if 'QMP' not in json.loads(self.stream.readline()):
            raise RuntimeError('missing QMP greeting')
        self.call('qmp_capabilities')

    def call(self, name, arguments=None):
        self.stream.write((json.dumps({'execute': name, 'arguments': arguments or {}}) + '\n').encode())
        self.stream.flush()
        while True:
            line = self.stream.readline()
            if not line:
                raise RuntimeError('QMP closed before command completion')
            reply = json.loads(line)
            if 'error' in reply:
                raise RuntimeError(reply['error'])
            if 'return' in reply:
                return reply['return']

    def command(self, command):
        if command not in {'menu', 'back', 'snapshot', 'enter', 'disp'}:
            raise ValueError('unsupported camera command')
        if self.process.poll() is not None:
            raise RuntimeError('QEMU has exited')
        self.process.stdin.write((command + '\n').encode('ascii'))
        self.process.stdin.flush()

    def snapshot(self, label, timeout=180):
        deadline = time.monotonic() + timeout
        while True:
            if self.closing.is_set():
                raise InterruptedError('camera window closed')
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f'no native {label} frame; see {self.output / "serial.log"}')
            try:
                value = self.frames.get(timeout=min(remaining, 1))
            except queue.Empty:
                if self.process.poll() is not None:
                    raise RuntimeError(f'QEMU exited with {self.process.returncode}')
                continue
            if isinstance(value, Exception):
                raise value
            meta, pages, ready = value
            if meta and meta.get('frame', 0) > self.frame:
                break
        settle = time.monotonic() + 3
        while time.monotonic() < settle:
            if self.closing.is_set():
                raise InterruptedError('camera window closed')
            try:
                value = self.frames.get(timeout=min(0.1, max(0.001, settle-time.monotonic())))
            except queue.Empty:
                continue
            if isinstance(value, Exception):
                raise value
            if value[0] and value[0]['frame'] >= meta['frame']:
                meta, pages, ready = value
        self.connect()
        self.call('stop')
        try:
            # Drain completed publications already written before QMP stopped the CPU.
            while True:
                try:
                    value = self.frames.get(timeout=0.2)
                except queue.Empty:
                    break
                if isinstance(value, Exception):
                    raise value
                if value[0] and value[0]['frame'] >= meta['frame']:
                    meta, pages, ready = value
            segments = capture.validate_segments(meta, pages, ready)
            data = bytearray()
            for index, segment in enumerate(segments):
                part = self.directory / f'page-{index}.bin'
                self.call('pmemsave', {'val': segment['physical'], 'size': segment['length'], 'filename': str(part)})
                block = part.read_bytes()
                if len(block) != segment['length']:
                    raise RuntimeError('truncated physical snapshot')
                data.extend(block)
            if capture.fingerprint(data) != meta['fingerprint_fnv1a64']:
                raise RuntimeError('native frame changed after publication')
            image = capture.decode_image(data)
            from PIL import Image
            preview = Image.new('RGBA', image.size, (0, 0, 0, 255))
            preview.alpha_composite(image)
            preview = preview.convert('RGB')
            preview.save(self.output / f'{label}.png')
            (self.output / f'{label}.rgba4444').write_bytes(data)
            evidence = dict(meta, raw_sha256=hashlib.sha256(data).hexdigest(),
                segments=segments, label=label, png=str(self.output / f'{label}.png'))
            (self.output / f'{label}.json').write_text(json.dumps(evidence, indent=2) + '\n')
            self.frame = meta['frame']
            return preview
        finally:
            self.call('cont')

    def disconnect(self):
        if self.stream:
            try:
                self.stream.close()
            except OSError:
                pass
            self.stream = None
        if self.channel:
            self.channel.close()
            self.channel = None

    def close(self):
        if self.process.poll() is None:
            deadline = time.monotonic() + 30
            while not self.endpoint.exists() and self.process.poll() is None and time.monotonic() < deadline:
                self.reader.join(0.1)
            error = None
            for _ in range(2):
                if self.process.poll() is not None:
                    break
                self.disconnect()
                try:
                    self.connect()
                    self.call('quit')
                    self.process.wait(timeout=10)
                except Exception as failure:
                    error = failure
            if self.process.poll() is None:
                self.disconnect()
                raise RuntimeError(f'QMP quit failed; QEMU PID={self.process.pid} remains owned; {error}')
        self.disconnect()
        self.reader.join(timeout=5)
        (self.output/'shutdown.json').write_text(json.dumps({'qemu_exit_code': self.process.poll(),
            'process_exited': True, 'shutdown': 'QMP quit or previously exited process'}, indent=2)+'\n')
        import shutil
        shutil.rmtree(self.directory)


def smoke():
    camera = Camera()
    try:
        camera.snapshot('main')
        camera.command('menu')
        camera.snapshot('menu-before-confirm')
        camera.command('enter')
        camera.snapshot('menu')
        main = json.loads((camera.output / 'main.json').read_text())
        menu = json.loads((camera.output / 'menu.json').read_text())
        if main['raw_sha256'] == menu['raw_sha256']:
            raise RuntimeError('MENU produced the same pixels as the main page')
        print(json.dumps({'output': str(camera.output), 'main': main['png'], 'menu': menu['png'],
            'native_frames_differ': True, 'visual_verification_required': True}, indent=2))
    finally:
        camera.close()


def window():
    import tkinter as tk
    from PIL import ImageTk
    root = tk.Tk()
    root.title('Sony A7 III — QEMU')
    root.resizable(False, False)
    display = tk.Canvas(root, width=640, height=480, bg='black', highlightthickness=0)
    display.pack()
    status = tk.StringVar(value='正在启动 A7M3 原厂界面…')
    tk.Label(root, textvariable=status).pack(fill='x')
    commands = queue.Queue()
    events = queue.Queue()
    controls = tk.Frame(root)
    controls.pack(pady=6)
    buttons = []
    for text, command in [('MENU', 'menu'), ('确认', 'enter'), ('返回', 'back'), ('DISP', 'disp'), ('刷新', 'snapshot')]:
        button = tk.Button(controls, text=text, width=12, command=lambda c=command: commands.put(c), state='disabled')
        button.pack(side='left', padx=4)
        buttons.append(button)
    root.bind('<m>', lambda _: commands.put('menu'))
    root.bind('<Escape>', lambda _: commands.put('back'))
    root.bind('<Return>', lambda _: commands.put('enter'))
    root.bind('<d>', lambda _: commands.put('disp'))
    closing = threading.Event()
    stopped = threading.Event()

    def worker():
        camera = None
        try:
            camera = Camera(closing)
            events.put(('image', camera.snapshot('main')))
            events.put(('status', f'原厂界面 · 日志和截图：{camera.output}'))
            while not closing.is_set():
                try:
                    command = commands.get(timeout=0.2)
                except queue.Empty:
                    continue
                if command is None:
                    break
                events.put(('busy', None))
                camera.command(command)
                events.put(('image', camera.snapshot(f'{command}-{camera.frame}')))
                events.put(('status', f'已处理 {command} · {camera.output}'))
        except Exception as error:
            events.put(('error', str(error)))
        finally:
            if camera:
                while True:
                    try:
                        camera.close()
                        break
                    except Exception as error:
                        events.put(('error', f'QEMU 关闭失败：{error}；再次关闭窗口以重试'))
                        while commands.get() is not None:
                            pass
            stopped.set()
            events.put(('closed', None))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()

    def close():
        if stopped.is_set():
            root.destroy()
            return
        closing.set()
        commands.put(None)
        status.set('正在关闭 QEMU…')
        for button in buttons:
            button.configure(state='disabled')

    def poll():
        try:
            while True:
                kind, value = events.get_nowait()
                if kind == 'image':
                    photo = ImageTk.PhotoImage(value)
                    display.delete('frame')
                    display.create_image(0, 0, anchor='nw', image=photo, tags='frame')
                    display.image = photo
                    for button in buttons:
                        button.configure(state='normal')
                elif kind in {'status', 'error'}:
                    status.set(value)
                elif kind == 'busy':
                    for button in buttons:
                        button.configure(state='disabled')
                elif kind == 'closed':
                    if closing.is_set():
                        root.destroy()
                        return
        except queue.Empty:
            pass
        root.after(100, poll)

    root.protocol('WM_DELETE_WINDOW', close)
    poll()
    root.mainloop()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--smoke', action='store_true', help='save main and MENU frames, then quit QEMU')
    args = parser.parse_args()
    smoke() if args.smoke else window()
