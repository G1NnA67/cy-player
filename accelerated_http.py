"""Bounded HTTP range downloads with verified chunks and native fallback.

Only enabled inside the separate download worker. No URLs or cookies are saved
in the resume manifest; completed chunks are keyed by media identity and content.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import threading
import time

from yt_dlp.downloader.http import HttpFD
from yt_dlp.networking import Request

CHUNK_SIZE = 1024 * 1024
CONNECTIONS = 4


class RangeUnavailable(Exception):
    pass


def content_range(response):
    match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', response.headers.get('Content-Range', ''))
    if response.status != 206 or not match:
        raise RangeUnavailable('Server did not honor a byte range')
    return tuple(map(int, match.groups()))


class RangeTransfer:
    def __init__(self, open_url, progress=lambda *a: None, status=lambda *a: None,
                 chunk_size=CHUNK_SIZE, connections=CONNECTIONS):
        self.open_url, self.progress, self.status = open_url, progress, status
        self.chunk_size, self.connections = chunk_size, connections
        self.stop = threading.Event()

    def probe(self, url, headers):
        start = time.monotonic()
        with self.open_url(url, {**headers, 'Range': 'bytes=0-65535', 'Accept-Encoding': 'identity'}, 4) as response:
            first, last, total = content_range(response)
            if first != 0 or last != min(65535, total - 1) or total <= 0:
                raise RangeUnavailable('Invalid probe range')
            data = response.read(last + 2)
            if len(data) != last + 1:
                raise RangeUnavailable('Incomplete probe')
        return {'url': url, 'total': total, 'head': hashlib.sha256(data).hexdigest(),
                'speed': len(data) / max(.001, time.monotonic() - start)}

    def download(self, filename, info):
        headers = dict(info.get('http_headers') or {})
        urls = list(dict.fromkeys([info['url'], *info.get('cy_backup_urls', [])]))[:3]
        self.status('正在选择下载线路…')
        candidates = []
        for url in urls:
            try:
                candidate = self.probe(url, headers)
                if candidates and (candidate['total'], candidate['head']) != (candidates[0]['total'], candidates[0]['head']):
                    continue
                candidates.append(candidate)
            except Exception:
                continue
        if not candidates:
            raise RangeUnavailable('No verified range source')
        candidates.sort(key=lambda item: item['speed'], reverse=True)
        total = candidates[0]['total']
        if total < self.chunk_size * 2:
            raise RangeUnavailable('Small file uses native download')
        if Path(str(filename) + '.part').exists():
            # Keep an existing native download resumable instead of discarding it.
            raise RangeUnavailable('Resume an existing native partial file')
        destination = Path(filename)
        identity = {'id': info.get('id'), 'format': info.get('format_id'),
                    'total': total, 'head': candidates[0]['head'], 'chunk_size': self.chunk_size}
        token = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()[:20]
        chunks = destination.parent / (destination.name + '.cy-parts') / token
        chunks.mkdir(parents=True, exist_ok=True)
        (chunks / 'manifest.json').write_text(json.dumps(identity, sort_keys=True))
        count = (total + self.chunk_size - 1) // self.chunk_size
        sizes = {i: min(self.chunk_size, total - i * self.chunk_size) for i in range(count)}
        done, current = {}, {}
        for i, size in sizes.items():
            path = chunks / f'{i:06d}.chunk'
            digest = path.with_suffix('.sha256')
            if path.is_file() and digest.is_file() and path.stat().st_size == size:
                if hashlib.sha256(path.read_bytes()).hexdigest() == digest.read_text():
                    done[i] = size
        initial = sum(done.values())
        started = time.monotonic()
        lock = threading.Lock()
        last_report = [0.0]

        def report(force=False):
            now = time.monotonic()
            if not force and now - last_report[0] < .2:
                return
            last_report[0] = now
            downloaded = sum(done.values()) + sum(current.values())
            speed = (downloaded - initial) / max(.001, now - started)
            self.progress(downloaded, total, speed or None,
                          (total - downloaded) / speed if speed > 0 else None)

        self.status('正在加速下载（最多 4 路连接）…')
        report(True)

        def fetch(index):
            start = index * self.chunk_size
            end = start + sizes[index] - 1
            path = chunks / f'{index:06d}.chunk'
            partial = path.with_suffix('.partial')
            for attempt in range(3):
                if self.stop.is_set():
                    raise RangeUnavailable('Range transfer stopped')
                candidate = candidates[attempt % len(candidates)]
                received = 0
                began = time.monotonic()
                try:
                    with self.open_url(candidate['url'], {**headers, 'Range': f'bytes={start}-{end}', 'Accept-Encoding': 'identity'}, 10) as response:
                        if content_range(response) != (start, end, total):
                            raise RangeUnavailable('Changed or ignored byte range')
                        digest = hashlib.sha256()
                        with partial.open('wb') as target:
                            while received < sizes[index]:
                                if self.stop.is_set():
                                    raise RangeUnavailable('Range transfer stopped')
                                data = response.read(min(16384, sizes[index] - received))
                                if not data:
                                    raise RangeUnavailable('Truncated chunk')
                                target.write(data); digest.update(data); received += len(data)
                                with lock:
                                    current[index] = received
                                    report()
                                elapsed = time.monotonic() - began
                                if attempt == 0 and len(candidates) > 1 and elapsed > 3 and received / elapsed < 128 * 1024:
                                    raise RangeUnavailable('Try alternate route for a slow chunk')
                            if response.read(1):
                                raise RangeUnavailable('Oversized chunk')
                    partial.replace(path)
                    path.with_suffix('.sha256').write_text(digest.hexdigest())
                    with lock:
                        done[index] = sizes[index]
                        current.pop(index, None)
                        report()
                    return
                except Exception as error:
                    with lock:
                        current.pop(index, None)
                    if attempt == 2 or self.stop.is_set():
                        raise RangeUnavailable('Range retries exhausted') from error
            raise RangeUnavailable('No completed chunk')

        try:
            with ThreadPoolExecutor(max_workers=self.connections) as pool:
                futures = [pool.submit(fetch, i) for i in sizes if i not in done]
                try:
                    for future in as_completed(futures):
                        future.result()
                except BaseException:
                    self.stop.set()
                    for future in futures:
                        future.cancel()
                    raise
            # Assembly is separate from native .part so an interrupted merge can
            # reuse all verified chunks, without changing native resume semantics.
            assembled = Path(str(filename) + '.cy-assembling')
            with assembled.open('wb') as output:
                for i in sizes:
                    with (chunks / f'{i:06d}.chunk').open('rb') as source:
                        shutil.copyfileobj(source, output)
            if assembled.stat().st_size != total:
                raise RangeUnavailable('Assembled length mismatch')
            assembled.replace(destination)
        except BaseException:
            self.stop.set()
            raise
        shutil.rmtree(chunks)
        try:
            chunks.parent.rmdir()
        except OSError:
            pass
        report(True)
        return total


class AcceleratedHttpFD(HttpFD):
    def real_download(self, filename, info_dict):
        if (info_dict.get('extractor_key', '').lower() not in ('bilibili', 'youtube')
                or info_dict.get('is_live') or info_dict.get('request_data')
                or filename == '-' or self.params.get('test')):
            return super().real_download(filename, info_dict)
        status = self.params.get('cy_status', lambda *args: None)

        def open_url(url, headers, timeout):
            return self.ydl.urlopen(Request(url, headers=headers, extensions={'timeout': timeout}))

        def progress(downloaded, total, speed, eta):
            self._hook_progress({'status': 'downloading', 'filename': filename,
                                 'downloaded_bytes': downloaded, 'total_bytes': total,
                                 'speed': speed, 'eta': eta}, info_dict)

        began = time.monotonic()
        try:
            total = RangeTransfer(open_url, progress, status).download(filename, info_dict)
        except RangeUnavailable:
            status('加速不可用，正在使用普通下载…')
            success = super().real_download(filename, info_dict)
            if success:
                parts = Path(str(filename) + '.cy-parts')
                if parts.is_dir():
                    shutil.rmtree(parts)
            return success
        self._hook_progress({'status': 'finished', 'filename': filename, 'downloaded_bytes': total,
                             'total_bytes': total, 'elapsed': time.monotonic() - began}, info_dict)
        return True


@contextmanager
def accelerated_downloads():
    """Use the pinned yt-dlp HTTP adapter only for this worker's lifetime."""
    from yt_dlp.downloader import PROTOCOL_MAP
    from yt_dlp.extractor.bilibili import BilibiliBaseIE
    original = BilibiliBaseIE.extract_formats
    previous = {p: PROTOCOL_MAP.get(p) for p in ('http', 'https')}

    def formats_with_backups(self, play_info):
        formats = original(self, play_info)
        sources = {}
        dash = play_info.get('dash') or {}
        streams = list(dash.get('video') or []) + list(dash.get('audio') or [])
        streams += list((dash.get('dolby') or {}).get('audio') or [])
        if (dash.get('flac') or {}).get('audio'):
            streams.append(dash['flac']['audio'])
        for stream in streams:
            main = stream.get('baseUrl') or stream.get('base_url') or stream.get('url')
            sources[main] = stream.get('backupUrl') or stream.get('backup_url') or []
        for fmt in formats:
            fmt['cy_backup_urls'] = [url for url in sources.get(fmt.get('url'), [])
                                     if isinstance(url, str) and url.startswith('https://')]
        return formats

    BilibiliBaseIE.extract_formats = formats_with_backups
    PROTOCOL_MAP.update(http=AcceleratedHttpFD, https=AcceleratedHttpFD)
    try:
        yield
    finally:
        BilibiliBaseIE.extract_formats = original
        for protocol, downloader in previous.items():
            if downloader is None:
                PROTOCOL_MAP.pop(protocol, None)
            else:
                PROTOCOL_MAP[protocol] = downloader
