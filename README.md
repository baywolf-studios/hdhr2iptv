# hdhr2iptv
Generates M3U files and a XMLTV file for HDHomeRun devices

## Help
```
usage: hdhr2iptv [-h] [-l LOG_FILE] [-s RUN_DAILY_HOUR] [-o OUTPUT_DIRECTORY] [-v]

Generates M3U files and a XMLTV file for HDHomeRun devices

options:
  -h, --help            show this help message and exit
  -l LOG_FILE, --log-file LOG_FILE
                        output log filename
  -s RUN_DAILY_HOUR, --run-daily-hour RUN_DAILY_HOUR
                        will loop and run daily at this hour
  -o OUTPUT_DIRECTORY, --output-directory OUTPUT_DIRECTORY
                        output directory for m3u and xml
  -v, --version         show program's version number and exit

Thanks for using hdhr2iptv! :)
```

## Usage

Here are some example snippets to help you get started creating a container.

### docker-compose
```yaml
services:
  hdhr2iptv:
    working-dir: /hdhr2iptv
    command: python hdhr2iptv.py --run-daily-hour 1
    image: python:3
    restart: unless-stopped
    volumes:
    - /etc/timezone:/etc/timezone:ro
    - /etc/localtime:/etc/localtime:ro
    - /path/to/hdhr2iptv:/hdhr2iptv:rw
version: '3.9'
```

### docker cli
```bash
docker run -d \
  --net=host \
  -v /etc/timezone:/etc/timezone:ro \
  -v /etc/localtime:/etc/localtime:ro \
  -v /path/to/hdhr2iptv:/hdhr2iptv:rw \
  --restart unless-stopped \
  --workdir /hdhr2iptv \
  python:3 python /hdhr2iptv/hdhr2iptv.py \
  --run-daily-hour 1
```
