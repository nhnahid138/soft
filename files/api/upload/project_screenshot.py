from __future__ import annotations

import cgi
import hashlib
import io
import json
import os
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler
from typing import Dict, Tuple

CLOUDINARY_CLOUD_NAME = os.environ.get('CLOUDINARY_CLOUD_NAME', 'dmpyzazve')
CLOUDINARY_API_KEY = os.environ.get('CLOUDINARY_API_KEY', '871143546716715')
CLOUDINARY_API_SECRET = os.environ.get('CLOUDINARY_API_SECRET', 'nFCf0PDUMbOw17P2vElGCb626rg')
CLOUDINARY_FOLDER = os.environ.get('CLOUDINARY_FOLDER', 'cassi-project-screens')


def build_signature(params: Dict[str, str], api_secret: str) -> str:
    ordered = '&'.join(f'{key}={params[key]}' for key in sorted(params))
    return hashlib.sha1(f'{ordered}{api_secret}'.encode('utf-8')).hexdigest()


def encode_multipart(fields: Dict[str, str], files: Dict[str, Tuple[str, bytes, str]]) -> Tuple[bytes, str]:
    boundary = f'----cassi{hashlib.md5(os.urandom(16)).hexdigest()}'
    buffer = io.BytesIO()

    def write_line(value: str) -> None:
        buffer.write(value.encode('utf-8'))
        buffer.write(b'\r\n')

    for name, value in fields.items():
        write_line(f'--{boundary}')
        write_line(f'Content-Disposition: form-data; name="{name}"')
        write_line('')
        write_line(value)

    for name, (filename, content, content_type) in files.items():
        write_line(f'--{boundary}')
        write_line(f'Content-Disposition: form-data; name="{name}"; filename="{filename}"')
        write_line(f'Content-Type: {content_type}')
        write_line('')
        buffer.write(content)
        buffer.write(b'\r\n')

    write_line(f'--{boundary}--')
    return buffer.getvalue(), boundary


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_type = self.headers.get('content-type', '')
        if 'multipart/form-data' not in content_type:
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Expected multipart/form-data'}).encode('utf-8'))
            return

        form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={
            'REQUEST_METHOD': 'POST',
            'CONTENT_TYPE': content_type,
        })

        file_item = form['file'] if 'file' in form else None
        if file_item is None or not getattr(file_item, 'filename', None):
            self.send_response(400)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': 'Missing file field'}).encode('utf-8'))
            return

        file_bytes = file_item.file.read()
        filename = os.path.basename(file_item.filename)
        mime_type = getattr(file_item, 'type', None) or 'application/octet-stream'
        timestamp = str(int(time.time()))
        signature = build_signature({'folder': CLOUDINARY_FOLDER, 'timestamp': timestamp}, CLOUDINARY_API_SECRET)

        post_fields = {
            'api_key': CLOUDINARY_API_KEY,
            'timestamp': timestamp,
            'folder': CLOUDINARY_FOLDER,
            'signature': signature,
        }
        post_files = {
            'file': (filename, file_bytes, mime_type),
        }
        body, boundary = encode_multipart(post_fields, post_files)

        request = urllib.request.Request(
            f'https://api.cloudinary.com/v1_1/{CLOUDINARY_CLOUD_NAME}/image/upload',
            data=body,
            headers={'Content-Type': f'multipart/form-data; boundary={boundary}'},
            method='POST',
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                payload = response.read()
                self.send_response(response.status)
                self.send_header('Content-Type', response.headers.get('Content-Type', 'application/json'))
                self.end_headers()
                self.wfile.write(payload)
        except urllib.error.HTTPError as error:
            payload = error.read()
            self.send_response(error.code)
            self.send_header('Content-Type', error.headers.get('Content-Type', 'application/json'))
            self.end_headers()
            self.wfile.write(payload)
        except Exception as error:
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'error': str(error)}).encode('utf-8'))
