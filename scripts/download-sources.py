#!/usr/bin/env python3
"""Archive Sony's ILCE-7M3 4.04 source packages and linked license pages.

Run with Python 3.10+; uses only the standard library and never extracts or
executes source packages. --self-test runs offline parser/format checks.
"""
import argparse
import base64
import bz2
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import gzip
import hashlib
from html.parser import HTMLParser
import io
import json
import lzma
import os
from pathlib import Path
import re
import tarfile
import tempfile
import time
from urllib.error import HTTPError
from urllib.parse import unquote, urldefrag, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
import zipfile

PAGE = 'https://oss.sony.net/Products/Linux/DI/ILCE-7M3_Ver404.html'
NOTICE = 'https://oss.sony.net/Products/Linux/notice.html'
HOSTS = {'oss.sony.net', 'prodgpl.blob.core.windows.net'}
ARCHIVE = re.compile(r'\.(?:tar(?:\.(?:gz|bz2|xz))?|tgz|tbz2|txz|zip|rpm)$', re.I)
BLOCK = 1024 * 1024


def now():
    return datetime.now(timezone.utc).isoformat()


def checked_url(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or parts.hostname not in HOSTS or parts.username or parts.password or parts.port not in (None, 80, 443):
        raise ValueError('URL outside Sony public source hosts: ' + url)
    return urlunsplit(('https', parts.netloc, parts.path, parts.query, ''))


class SonyRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return super().redirect_request(req, fp, code, msg, headers, checked_url(newurl))


def request(url):
    return build_opener(SonyRedirect()).open(Request(checked_url(url), headers={
        'User-Agent': 'ILCE-7M3-public-source-archiver/1.0 (Python urllib)',
        'Accept-Encoding': 'identity',
    }), timeout=90)


class Links(HTMLParser):
    def __init__(self, base):
        super().__init__(convert_charrefs=True)
        self.base = base
        self.urls = []

    def add(self, value):
        if value:
            self.urls.append(urldefrag(urljoin(self.base, value.strip()))[0])

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag in ('a', 'area'):
            self.add(attrs.get('href'))
        elif tag in ('iframe', 'frame'):
            self.add(attrs.get('src'))
        elif tag == 'meta' and attrs.get('http-equiv', '').lower() == 'refresh':
            match = re.search(r'url\s*=\s*[\'"]?([^\'";]+)', attrs.get('content', ''), re.I)
            if match:
                self.add(match[1])
        elif tag == 'form':
            # shortcut: only public GET link forms; add form fields if Sony introduces one.
            if attrs.get('method', 'get').lower() == 'get':
                self.add(attrs.get('action'))


def relevant(url):
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or parts.hostname not in HOSTS:
        return False
    path = unquote(parts.path)
    if ARCHIVE.search(path):
        return True
    if url == NOTICE:
        return True
    name = path.rsplit('/', 1)[-1].lower()
    return (path.startswith('/Products/Linux/DI/') and name.endswith(('.html', '.htm'))
            and not name.startswith(('category', 'index')) or
            path.startswith('/Products/Linux/') and any(word in path.lower() for word in ('license', 'licence', 'eula', 'download')))


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(BLOCK), b''):
            digest.update(chunk)
    return digest.hexdigest()


def checkpoint(path, report):
    part = path.with_name(path.name + '.part')
    if path.is_symlink() or part.is_symlink():
        raise ValueError('Refusing manifest symlink')
    with part.open('w', encoding='utf-8') as stream:
        json.dump(report, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    part.replace(path)


def validate(path, name):
    with path.open('rb') as stream:
        first = stream.read(512)
    if not first or first.lstrip().lower().startswith((b'<!doctype html', b'<html', b'<?xml', b'<error')):
        raise ValueError('Empty package or HTML/XML error page: ' + name)
    if name.lower().endswith('.rpm'):
        if len(first) < 112 or first[:4] != b'\xed\xab\xee\xdb' or first[96:100] != b'\x8e\xad\xe8\x01':
            raise ValueError('Invalid RPM lead/signature header: ' + name)
        return {'format': 'rpm', 'check': 'RPM lead and signature-header magic (payload not unpacked)'}
    if name.lower().endswith('.zip'):
        with zipfile.ZipFile(path) as archive:
            count = len(archive.infolist())
            bad = archive.testzip()
        if not count or bad:
            raise ValueError('Empty/corrupt ZIP: ' + str(bad))
        return {'format': 'zip', 'members': count, 'check': 'directory and every member CRC'}
    with tarfile.open(path, 'r:*') as archive:
        count = sum(1 for _ in archive)
    if not count:
        raise ValueError('Empty TAR: ' + name)
    lower = name.lower()
    opener = gzip.open if lower.endswith(('.gz', '.tgz')) else bz2.open if lower.endswith(('.bz2', '.tbz2')) else lzma.open if lower.endswith(('.xz', '.txz')) else None
    if opener:
        with opener(path, 'rb') as stream:
            for _ in iter(lambda: stream.read(BLOCK), b''):
                pass
    return {'format': 'tar', 'members': count, 'check': 'TAR headers and complete compressed-stream integrity'}


def metadata(response):
    return {'final_url': checked_url(response.geturl()), 'http_status': response.status,
            'content_type': response.headers.get('Content-Type'),
            'content_length': response.headers.get('Content-Length'),
            'content_md5': response.headers.get('Content-MD5'),
            'last_modified': response.headers.get('Last-Modified'),
            'etag': response.headers.get('ETag')}


def discover(dest, report):
    queue = [(PAGE, None), (NOTICE, PAGE)]
    seen = set()
    packages = {}
    while queue:
        url, source = queue.pop(0)
        url = checked_url(url)
        if url in seen:
            continue
        seen.add(url)
        if len(seen) > 100:
            raise ValueError('Exceeded 100 source/license pages; inspect changed site')
        name = 'source-page.html' if url == PAGE else 'notice.html' if url == NOTICE else hashlib.sha256(url.encode()).hexdigest()[:16] + '-' + Path(urlsplit(url).path).name
        path = dest / 'pages' / name
        part = path.with_name(path.name + '.part')
        if path.is_symlink() or part.is_symlink():
            raise ValueError('Refusing page symlink: ' + str(path))
        with request(url) as response:
            raw = response.read(4 * BLOCK + 1)
            record = metadata(response)
        if len(raw) > 4 * BLOCK or b'<html' not in raw[:4096].lower():
            raise ValueError('Unexpected source/license page content: ' + url)
        part.write_bytes(raw)
        part.replace(path)
        text = raw.decode('utf-8', errors='replace')
        if url == PAGE and 'ILCE-7M3 Ver.4.04' not in text:
            raise ValueError('Sony source page model/version differs')
        record.update(url=url, source_page=source, path=str(path.relative_to(dest)), bytes=len(raw),
                      sha256=sha(path), fetched_at=now())
        parser = Links(record['final_url'])
        parser.feed(text)
        record['relevant_links'] = sorted({checked_url(link) for link in parser.urls if relevant(link)})
        report['pages'][record['path']] = record
        for link in record['relevant_links']:
            if ARCHIVE.search(unquote(urlsplit(link).path)):
                packages.setdefault(link, set()).add(url)
            elif link not in seen:
                queue.append((link, url))
        checkpoint(dest / 'manifest.json', report)
    if not packages:
        raise ValueError('No source packages found')
    names = {url: unquote(urlsplit(url).path.rsplit('/', 1)[-1]) for url in packages}
    if len(set(names.values())) != len(names) or any(not re.fullmatch(r'[A-Za-z0-9_.+-]+', name) or name in ('.', '..') for name in names.values()):
        raise ValueError('Duplicate or unsafe package filename')
    return packages, names


def download(dest, url, name, origins, previous):
    path = dest / name
    part = dest / (name + '.part')
    if path.is_symlink() or part.is_symlink():
        raise ValueError('Refusing package symlink: ' + name)
    if previous and previous.get('url') == url and path.is_file() and path.stat().st_size == previous.get('bytes') and sha(path) == previous.get('sha256'):
        previous.update(validation=validate(path, name), source_pages=sorted(origins), reused=True)
        return previous
    record = {'url': url, 'source_pages': sorted(origins), 'path': name, 'attempts': []}
    for attempt in range(1, 4):
        started = now()
        try:
            with request(url) as response, part.open('wb') as output:
                record.update(metadata(response))
                digest = hashlib.sha256()
                md5 = hashlib.md5()
                size = 0
                for chunk in iter(lambda: response.read(BLOCK), b''):
                    output.write(chunk)
                    digest.update(chunk)
                    md5.update(chunk)
                    size += len(chunk)
                output.flush()
                os.fsync(output.fileno())
            if not size or record['content_length'] is not None and size != int(record['content_length']):
                raise ValueError('Empty or truncated response')
            if 'html' in (record['content_type'] or '').lower():
                raise ValueError('Server returned HTML for an archive')
            if record['content_md5'] and base64.b64encode(md5.digest()).decode() != record['content_md5']:
                raise ValueError('Server Content-MD5 mismatch')
            record['validation'] = validate(part, name)
            if sha(part) != digest.hexdigest():
                raise ValueError('Disk readback SHA256 mismatch')
            part.replace(path)
            record.update(bytes=size, sha256=digest.hexdigest(), downloaded_at=now(), reused=False)
            record['attempts'].append({'attempt': attempt, 'started_at': started, 'ok': True})
            return record
        except Exception as error:
            failure = {'attempt': attempt, 'started_at': started, 'ok': False,
                       'error': type(error).__name__ + ': ' + str(error)}
            if isinstance(error, HTTPError):
                failure['http_status'] = error.code
                part.write_bytes(error.read(BLOCK))
                error.close()
            if part.exists():
                saved = dest / 'failures' / (name + '.' + str(time.time_ns()) + '.part')
                saved.parent.mkdir(exist_ok=True)
                part.replace(saved)
                failure.update(path=str(saved.relative_to(dest)), bytes=saved.stat().st_size, sha256=sha(saved))
            record['attempts'].append(failure)
            if attempt == 3:
                record['error'] = failure['error']
                return record
            time.sleep(attempt)
    raise AssertionError('unreachable')


def self_test():
    parser = Links(PAGE)
    parser.feed('<a href="../license/agree.html">License</a><a href="x.tar.gz#x">x</a>'
                '<meta http-equiv="refresh" content="0; URL=next.htm">')
    assert parser.urls == ['https://oss.sony.net/Products/Linux/license/agree.html',
                           'https://oss.sony.net/Products/Linux/DI/x.tar.gz',
                           'https://oss.sony.net/Products/Linux/DI/next.htm']
    assert relevant(parser.urls[0]) and relevant(parser.urls[1])
    assert not relevant('https://oss.sony.net/Products/Linux/DI/category01.html')
    assert not relevant('https://example.com/evil.tar.gz')
    try:
        checked_url('https://oss.sony.net@example.com/evil.tar.gz')
    except ValueError:
        pass
    else:
        raise AssertionError('Host validation failed')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'archive.part'
        for name in ('source.tar.gz', 'source.zip', 'source.src.rpm'):
            path.write_text('<!DOCTYPE html><html>error</html>')
            try:
                validate(path, name)
            except ValueError:
                pass
            else:
                raise AssertionError('Accepted HTML as ' + name)
        with tarfile.open(path, 'w:gz') as archive:
            info = tarfile.TarInfo('hello.txt')
            info.size = 5
            archive.addfile(info, io.BytesIO(b'hello'))
        assert validate(path, 'source.tar.gz')['members'] == 1
        valid_tar = path.read_bytes()
        damaged = bytearray(valid_tar)
        damaged[-8] ^= 1
        path.write_bytes(damaged)
        try:
            validate(path, 'source.tar.gz')
        except (OSError, tarfile.TarError):
            pass
        else:
            raise AssertionError('Accepted corrupt gzip CRC')
        with zipfile.ZipFile(path, 'w') as archive:
            archive.writestr('hello.txt', 'hello')
        assert validate(path, 'source.zip')['members'] == 1
        from unittest.mock import patch
        for label, payload, content_type, length, succeeds in (
                ('good', valid_tar, 'application/gzip', len(valid_tar), True),
                ('html', b'<html>error</html>', 'text/html', 18, False),
                ('truncated', valid_tar, 'application/gzip', len(valid_tar) + 1, False)):
            name = label + '.tar.gz'
            target = Path(tmp) / name
            target.write_bytes(b'existing file')
            def fake_request(url):
                response = io.BytesIO(payload)
                response.headers = {'Content-Type': content_type, 'Content-Length': str(length)}
                response.status = 200
                response.geturl = lambda: url
                return response
            with patch.dict(globals(), {'request': fake_request}), patch.object(time, 'sleep'):
                record = download(Path(tmp), PAGE + '/' + name, name, {PAGE}, None)
            assert ('error' not in record) == succeeds
            assert target.read_bytes() == (payload if succeeds else b'existing file')
            assert not target.with_name(name + '.part').exists()
            if not succeeds:
                assert len(record['attempts']) == 3
                assert all((Path(tmp) / entry['path']).read_bytes() == payload for entry in record['attempts'])
    print('SELF_TEST_OK', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dest', type=Path, default=Path(__file__).resolve().parents[1] / 'sources' / 'sony-ilce7m3-ver404')
    parser.add_argument('--workers', type=int, choices=range(1, 9), default=4)
    parser.add_argument('--self-test', action='store_true')
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    dest = args.dest.resolve()
    dest.mkdir(parents=True, exist_ok=True)
    (dest / 'pages').mkdir(exist_ok=True)
    previous = json.loads((dest / 'manifest.json').read_text()) if (dest / 'manifest.json').exists() else {}
    report = {'source_page': PAGE, 'model': 'ILCE-7M3', 'version': '4.04', 'started_at': now(),
              'complete': False, 'workers': args.workers, 'pages': {}, 'files': {}, 'errors': {},
              'validation_scope': 'Page discovery, Content-Length/Content-MD5 when provided, disk-readback SHA256, TAR structure/compression or ZIP CRC, RPM lead/header magic; no extraction or execution.'}
    checkpoint(dest / 'manifest.json', report)
    try:
        packages, names = discover(dest, report)
    except Exception as error:
        report['errors']['discovery'] = type(error).__name__ + ': ' + str(error)
        checkpoint(dest / 'manifest.json', report)
        raise
    report.update(expected_count=len(packages), listed_files=sorted(names.values()))
    checkpoint(dest / 'manifest.json', report)
    print('SOURCE_LIST', len(packages), 'pages', len(report['pages']), flush=True)
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(download, dest, url, names[url], origins, previous.get('files', {}).get(names[url])): names[url] for url, origins in sorted(packages.items())}
        for future in as_completed(futures):
            name = futures[future]
            try:
                record = future.result()
                if record.get('error'):
                    report['errors'][name] = record
                    print('SOURCE_FAILED', name, record['error'], flush=True)
                else:
                    report['files'][name] = record
                    print('SOURCE_OK', name, record['bytes'], record['sha256'], flush=True)
            except Exception as error:
                report['errors'][name] = type(error).__name__ + ': ' + str(error)
                print('SOURCE_FAILED', name, str(error), flush=True)
            report['total_bytes'] = sum(r['bytes'] for r in report['files'].values())
            checkpoint(dest / 'manifest.json', report)
    report['finished_at'] = now()
    report['complete'] = not report['errors'] and len(report['files']) == len(packages)
    checkpoint(dest / 'manifest.json', report)
    checksums = ''.join(record['sha256'] + '  ' + record['path'] + '\n' for _, record in sorted(report['files'].items()))
    checksums += ''.join(record['sha256'] + '  ' + record['path'] + '\n' for _, record in sorted(report['pages'].items()))
    part = dest / 'SHA256SUMS.part'
    if part.is_symlink() or (dest / 'SHA256SUMS').is_symlink():
        raise ValueError('Refusing checksum symlink')
    part.write_text(checksums)
    part.replace(dest / 'SHA256SUMS')
    print('SOURCE_COMPLETE' if report['complete'] else 'SOURCE_INCOMPLETE', len(report['files']), report['total_bytes'], flush=True)
    return 0 if report['complete'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
