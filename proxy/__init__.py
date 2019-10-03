import boto3
import botocore
import hashlib
import logging
from proxy.cache import LRUCache
from proxy.cache import NoOpCache
import tempfile


class CachingS3Proxy(object):
    def __init__(self, capacity=(10 * 10**9), cache_dir=tempfile.gettempdir()):
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
        if capacity:
            self.cache = LRUCache(capacity, cache_dir)
        else:
            self.cache = NoOpCache()
        self.s3 = boto3.resource('s3')

    def proxy_s3_bucket(self, environ, start_response):
        """proxy private s3 buckets"""
        path_info = environ.get('PATH_INFO', '')
        if path_info == '/':
            status = '200 OK'
            response_headers = [('Content-type', 'text/plain')]
            start_response(status, response_headers)
            return ['Caching S3 Proxy']

        path_info = path_info.lstrip('/')
        (bucket, key) = path_info.split('/', 1)
        status = '200 OK'
        response_headers = []
        try:
            # this is a compatibility hack for pip.  pip expects the
            # web server to serve an index page, so we need to
            # generate one if the path is a 'directory'
            if key.endswith('/'):
                listing = self.fetch_directory_listing(bucket, key)
                s3_result = self.serve_index(bucket, key, listing)
                response_headers = [('Content-type', 'text/html')]
            else:
                s3_result = self.fetch_s3_object(bucket, key)
        except botocore.exceptions.ClientError as ce:
            s3_result = [ce.response['Error']['Message']]
            status = '404 NOT FOUND'

        start_response(status, response_headers)
        return s3_result

    def fetch_s3_object(self, bucket, key):
        m = hashlib.md5()
        m.update(bucket + key)
        cache_key = m.hexdigest()

        try:
            return self.cache[cache_key]
        except KeyError:
            self.logger.debug('cache miss for %s' % cache_key)

            obj = self.s3.Object(bucket, key).get()
            body = obj['Body'].read()
            self.cache[cache_key] = body
            return [body]

    def fetch_directory_listing(self, bucket, key):
        """Fetch a listing of the ersatz 'directory'.  S3 is an object store
        so it doesn't have directories as such, but we're pretending
        that it's a file system.

        """
        listing = next(iter(boto3.client('s3').get_paginator('list_objects').paginate(Bucket=bucket, Prefix=key)))

        # since we're asking for a listing, it's valid to have 0
        # objects in the results, but we want to pretend that it's a
        # directory that doesn't exist so we raise the same error that
        # boto raises when you try to fetch a key that doesn't exist
        if 'Contents' not in listing:
            raise botocore.exceptions.ClientError({'Error': {'Message': '"Directory" {key} not Found'.format(key=key)}}, 'GET')

        # we want to return only the objects that are in this
        # 'directory' and not any of its 'subdirectories', so screen
        # out objects in 'subdirectories', i.e., objects with '/' in
        # the path
        return [file for file in listing['Contents'] if '/' not in file['Key'][len(key):]]

    def serve_index(self, bucket, base_key, listing):
        """Generate an HTML index page from a listing of objects."""

        yield "<html><head><title>Package Index</title></head><body>"
        for object in listing:
            yield('<a href="/{bucket}/{file}">{file}</a><br/>'.format(bucket=bucket, file=object['Key']))
        yield "</body></html>"
