# hdhr2xml
Generates a XMLTV file for HDHomeRun devices

## Help
```
usage: hdhr2xml [-h] [-l LOG_FILE] [-o OUTPUT_FILE] [-s SLEEP_TIME] [-f] [-v]

Generates a XMLTV file for HDHomeRun devices

options:
  -h, --help            show this help message and exit
  -l LOG_FILE, --log-file LOG_FILE
                        output log filename
  -o OUTPUT_FILE, --output-file OUTPUT_FILE
                        output xml filename
  -s SLEEP_TIME, --sleep-time SLEEP_TIME
                        number of seconds to sleep before looping
  -f, --favorites-only  only retrieve epg for favorite channels
  -v, --version         show program's version number and exit

Thanks for using hdhr2xml! :)
```

## Usage

Here are some example snippets to help you get started creating a container.

### docker-compose
```yaml
services:
  hdhr2xml:
    command:
    - python
    - /hdhr2xml/hdhr2xml.py
    - --output-file=/hdhr2xml/xmltv.xml
    - --log-file=/hdhr2xml/hdhr2xml.log
    - --sleep-time=3600
    - --favorites-only
    image: python:3
    restart: unless-stopped
    volumes:
    - /etc/timezone:/etc/timezone:ro
    - /etc/localtime:/etc/localtime:ro
    - /path/to/hdhr2xml:/hdhr2xml:rw
version: '3.9'
```

### docker cli
```bash
docker run -d \
  -v /etc/timezone:/etc/timezone:ro \
  -v /etc/localtime:/etc/localtime:ro \
  -v /path/to/hdhr2xml:/hdhr2xml:rw \
  --restart unless-stopped \
  python:3 python /hdhr2xml/hdhr2xml.py \
  --output-file=/hdhr2xml/xmltv.xml \
  --log-file=/hdhr2xml/hdhr2xml.log \
  --sleep-time=3600 \
  --favorites-only 
```
