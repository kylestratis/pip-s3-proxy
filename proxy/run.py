#!/usr/bin/env python
import os
from proxy import CachingS3Proxy
import subprocess
import sys
import tempfile
import threading
from wsgiref.simple_server import make_server


def serve_forever(host, port, hook):
    httpd = make_server(host, port, hook)
    print('Serving HTTP on port %s...' % port)
    httpd.serve_forever()


def pipsss():

    # set up the proxy on a daemon thread so we don't have to worry
    # about cleaning it up - we'll run pip synchronously and exit when
    # it's done
    p = CachingS3Proxy(capacity=0, cache_dir='/dev/null')
    port = int(os.environ.get('PORT', 8000))
    proxy = threading.Thread(name='proxy', target=lambda: serve_forever('localhost', port, p.proxy_s3_bucket))
    proxy.daemon = True
    proxy.start()

    # run pip with the params passed into this program
    pip_args = ['pip'] + sys.argv[1:]
    subprocess.check_call(pip_args)


def main():
    capacity = int(os.environ.get('CAPACITY', 1000000000))
    cache_dir = os.environ.get('CACHEDIR', tempfile.gettempdir())
    p = CachingS3Proxy(capacity, cache_dir)
    port = int(os.environ.get('PORT', 8000))
    serve_forever('', port, p.proxy_s3_bucket)


if __name__ == '__main__':
    main()
