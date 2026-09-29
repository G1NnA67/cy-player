import io
import hashlib
import json
import os
from pathlib import Path
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from accelerated_http import RangeTransfer, RangeUnavailable, AcceleratedHttpFD, accelerated_downloads
from yt_dlp.downloader.http import HttpFD

PROJECT = Path(__file__).resolve().parent
ROOT = PROJECT.parent if PROJECT.name == "project" else PROJECT
(ROOT / "tmp").mkdir(exist_ok=True)

class Response(io.BytesIO):
    def __init__(self, data, first, last, total, status=206):
        super().__init__(data)
        self.status = status
        self.headers = {'Content-Range': f'bytes {first}-{last}/{total}'}

class RangeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT/'tmp')
        self.folder = Path(self.temp.name)
        self.data = bytes(range(256)) * 4096 + b'end'
        self.calls = []
        self.info = {'url': 'https://main.test/media', 'id': 'video', 'format_id': '1080'}

    def tearDown(self):
        self.temp.cleanup()

    def opener(self, url, headers, timeout):
        start, end = map(int, headers['Range'][6:].split('-'))
        end = min(end, len(self.data)-1)
        self.calls.append((url, start, end))
        return Response(self.data[start:end+1], start, end, len(self.data))

    def transfer(self, opener=None):
        return RangeTransfer(opener or self.opener, chunk_size=131072, connections=4)

    def test_exact_bytes_parallel_assembly_and_cleanup(self):
        progress=[]
        t=self.transfer();t.progress=lambda *args: progress.append(args)
        path=self.folder/'media.mp4';t.download(path,self.info)
        self.assertEqual(path.read_bytes(),self.data)
        self.assertEqual(progress[-1][:2],(len(self.data),len(self.data)))
        self.assertFalse(Path(str(path)+'.cy-parts').exists())

    def test_server_ignores_range_never_creates_output(self):
        def ignore(url,headers,timeout):return Response(self.data,0,len(self.data)-1,len(self.data),200)
        path=self.folder/'media.mp4'
        with self.assertRaises(RangeUnavailable):self.transfer(ignore).download(path,self.info)
        self.assertFalse(path.exists())

    def test_truncated_chunk_is_not_accepted(self):
        def truncated(url,headers,timeout):
            r=self.opener(url,headers,timeout)
            if headers['Range']!='bytes=0-65535':
                r=Response(r.getvalue()[:-1],*map(int,headers['Range'][6:].split('-')),len(self.data))
            return r
        path=self.folder/'media.mp4'
        with self.assertRaises(RangeUnavailable):self.transfer(truncated).download(path,self.info)
        self.assertFalse(path.exists())

    def test_backup_used_when_primary_chunk_fails(self):
        def flaky(url,headers,timeout):
            if 'main.test' in url and headers['Range']!='bytes=0-65535':raise OSError('offline')
            return self.opener(url,headers,timeout)
        info={**self.info,'cy_backup_urls':['https://backup.test/media']}
        path=self.folder/'media.mp4';self.transfer(flaky).download(path,info)
        self.assertEqual(path.read_bytes(),self.data)
        self.assertTrue(any('backup.test' in url and end>65535 for url,start,end in self.calls))

    def test_mismatched_backup_is_excluded(self):
        def mismatch(url,headers,timeout):
            r=self.opener(url,headers,timeout)
            if 'backup.test' in url:return Response(b'x'*len(r.getvalue()),0,65535,len(self.data))
            return r
        info={**self.info,'cy_backup_urls':['https://backup.test/media']}
        path=self.folder/'media.mp4';self.transfer(mismatch).download(path,info)
        self.assertEqual(path.read_bytes(),self.data)
        self.assertEqual(sum('backup.test' in url for url,_,_ in self.calls),1)

    def test_resume_reuses_verified_chunks_after_failure(self):
        def fail_later(url,headers,timeout):
            start=int(headers['Range'][6:].split('-')[0])
            if start>=262144:time.sleep(.02);raise OSError('disconnect')
            return self.opener(url,headers,timeout)
        path=self.folder/'media.mp4'
        with self.assertRaises(RangeUnavailable):self.transfer(fail_later).download(path,self.info)
        saved=list(self.folder.rglob('*.chunk'));self.assertTrue(saved)
        saved_indices={int(p.stem) for p in saved}
        self.calls=[];self.transfer().download(path,self.info)
        self.assertEqual(path.read_bytes(),self.data)
        fetched={start//131072 for _,start,end in self.calls if end!=65535}
        self.assertFalse(saved_indices & fetched)

    def test_corrupted_saved_chunk_is_redownloaded(self):
        t=self.transfer();t.connections=1
        def fail_later(url,headers,timeout):
            if int(headers['Range'][6:].split('-')[0])>=131072:raise OSError('disconnect')
            return self.opener(url,headers,timeout)
        t.open_url=fail_later;path=self.folder/'media.mp4'
        with self.assertRaises(RangeUnavailable):t.download(path,self.info)
        chunk=next(self.folder.rglob('*.chunk'));chunk.write_bytes(b'x'*chunk.stat().st_size)
        self.transfer().download(path,self.info)
        self.assertEqual(path.read_bytes(),self.data)

    def test_native_partial_is_preserved(self):
        path=self.folder/'media.mp4';partial=Path(str(path)+'.part');partial.write_bytes(b'existing')
        with self.assertRaises(RangeUnavailable):self.transfer().download(path,self.info)
        self.assertEqual(partial.read_bytes(),b'existing')

    def test_adapter_falls_back_to_native(self):
        import yt_dlp
        with yt_dlp.YoutubeDL({'quiet':True}) as ydl:
            fd=AcceleratedHttpFD(ydl,{'quiet':True})
            with patch.object(RangeTransfer,'download',side_effect=RangeUnavailable('no ranges')), patch.object(HttpFD,'real_download',return_value=True) as native:
                self.assertTrue(fd.real_download(str(self.folder/'file'),{**self.info,'extractor_key':'Youtube'}))
                native.assert_called_once()

    def test_registration_is_scoped(self):
        from yt_dlp.downloader import PROTOCOL_MAP
        previous=dict(PROTOCOL_MAP)
        with accelerated_downloads():self.assertIs(PROTOCOL_MAP['https'],AcceleratedHttpFD)
        self.assertEqual(PROTOCOL_MAP,previous)

if __name__=='__main__':unittest.main()
