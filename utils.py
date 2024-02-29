import argparse
import json
import logging
import os
import time
import urllib.request
from datetime import datetime, timezone, timedelta

LOCAL_TIMEZONE = datetime.now(timezone.utc).astimezone().tzinfo

def delete_files_created_30_days_ago(directory):
    thirty_days_ago = datetime.now() - timedelta(days=30)
    
    for file in os.listdir(directory):
        file_path = os.path.join(directory, file)
        if os.path.isfile(file_path):
            created_time = datetime.fromtimestamp(os.path.getctime(file_path))
            if created_time < thirty_days_ago:
                os.remove(file_path)

def sleep_until_hour(hour):
    today = datetime.today()
    future = datetime(today.year, today.month, today.day, hour, 0)
    if today.timestamp() > future.timestamp():
        future += timedelta(days=1)

    logging.info(f"Sleeping until: {future}")
    time.sleep((future - today).total_seconds())


def directory(raw_path):
    if not os.path.isdir(raw_path):
        raise argparse.ArgumentTypeError(
            '"{}" is not an existing directory'.format(raw_path)
        )
    return os.path.abspath(raw_path)


def convert_timestamp_to_xmltv_datetime(timestamp):
    return datetime.fromtimestamp(timestamp, tz=LOCAL_TIMEZONE).strftime(
        "%Y%m%d%H%M%S %z"
    )

def save_json_to_file(filename, json_data):
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    with open(filename, "w") as filename:
        json.dump(json_data, filename)


def load_json_from_file(filename):
    with open(filename, "r") as cache_file:
        return json.load(cache_file)


def http_get_json(url):
    try:
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read().decode(r.info().get_param("charset") or "utf-8"))
            return data
    except urllib.error.HTTPError as e:
        logging.exception(e.message)
        if e.status != 307 and e.status != 308:
            raise
        redirected_url = urllib.parse.urljoin(url, e.headers["Location"])
        return http_get_json(redirected_url)


def http_get_json_with_retry(url, max_retries=5, retry_delay=1):
    for retry_count in range(1, max_retries + 1):
        try:
            time.sleep(retry_delay * retry_count)
            return http_get_json(url)
        except urllib.error.URLError as e:
            if retry_count != max_retries:
                logging.warning(f"Attempting request {retry_count} for: {url}")
                continue
            else:
                logging.exception(f"Reached max retries of {max_retries} for: {url}")
                raise
