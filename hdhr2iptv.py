import argparse
import datetime
import json
import logging
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone, timedelta
from libhdhr import get_hdhr_devices

LOCAL_TIMEZONE = datetime.now(timezone.utc).astimezone().tzinfo


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


def timestamp_to_xmltv_datetime(timestamp):
    return datetime.fromtimestamp(timestamp, tz=LOCAL_TIMEZONE).strftime(
        "%Y%m%d%H%M%S %z"
    )


def parse_program(xml_root, program, channel_number):
    title = program["Title"]
    logging.info(f"Parsing Channel: {channel_number} Program: {title}")

    xml_program = ET.SubElement(xml_root, "programme", channel=channel_number)

    xml_program.set("start", timestamp_to_xmltv_datetime(program["StartTime"]))

    xml_program.set("stop", timestamp_to_xmltv_datetime(program["EndTime"]))

    ET.SubElement(xml_program, "title", lang="en").text = title

    if "EpisodeTitle" in program:
        ET.SubElement(xml_program, "sub-title", lang="en").text = program[
            "EpisodeTitle"
        ]

    if "Synopsis" in program:
        ET.SubElement(xml_program, "desc").text = program["Synopsis"]

    # Add a blank credits to satisfy Plex
    ET.SubElement(xml_program, "credits").text = ""

    if "EpisodeNumber" in program:
        # Fake the xml version
        season = str(int(program["EpisodeNumber"].split("S")[1].split("E")[0]) - 1)
        episode = str(int(program["EpisodeNumber"].split("S")[1].split("E")[1]) - 1)
        ET.SubElement(xml_program, "episode-num", system="xmltv_ns").text = (
            season + "." + episode + "."
        )

        ET.SubElement(xml_program, "episode-num", system="onscreen").text = program[
            "EpisodeNumber"
        ]

        ET.SubElement(xml_program, "episode-num", system="SxxExx").text = program[
            "EpisodeNumber"
        ]

        ET.SubElement(xml_program, "category", lang="en").text = "Series"

    if "ImageURL" in program:
        ET.SubElement(xml_program, "icon", src=program["ImageURL"])

    xmlAudio = ET.SubElement(xml_program, "audio")
    ET.SubElement(xmlAudio, "stereo").text = "stereo"
    ET.SubElement(xml_program, "subtitles", type="teletext")

    is_movie = False
    if "Filter" in program:
        for category in program["Filter"]:
            ET.SubElement(xml_program, "category", lang="en").text = category
            if str(category).lower() == "movies":
                ET.SubElement(xml_program, "category", lang="en").text = "Movie"
                is_movie = True

    if not is_movie:
        if "OriginalAirdate" in program:

            original_air_date = datetime.fromtimestamp(
                program["OriginalAirdate"], timezone.utc
            ).date()
            current_air_date = datetime.fromtimestamp(program["StartTime"]).date()
            if original_air_date < current_air_date:
                ET.SubElement(xml_program, "previously-shown")
                ET.SubElement(xml_program, "previously-aired")
            else:
                ET.SubElement(
                    xml_program,
                    "new",
                )
            ET.SubElement(
                xml_program, "episode-num", system="original_air_date"
            ).text = str(original_air_date)
        else:
            ET.SubElement(
                xml_program,
                "new",
            )
            ET.SubElement(
                xml_program, "episode-num", system="original_air_date"
            ).text = str(date.today())

    # Return the endtime so we know where to start from on next loop.
    return program["EndTime"]


def parse_channel(xml_root, channel):
    channel_number = channel.get("GuideNumber")

    logging.info(f"Parsing Channel: {channel_number}")

    xml_channel = ET.SubElement(xml_root, "channel", id=channel_number)

    ET.SubElement(xml_channel, "display-name").text = channel_number

    ET.SubElement(xml_channel, "display-name").text = channel.get("GuideName")

    if "Affiliate" in channel:
        ET.SubElement(xml_channel, "display-name").text = channel.get("Affiliate")

    if "ImageURL" in channel:
        ET.SubElement(xml_channel, "icon", src=channel.get("ImageURL"))

    return xml_channel


def http_get_json(url):
    try:
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read().decode(r.info().get_param("charset") or "utf-8"))
            return data
    except urllib.error.HTTPError as e:
        if e.status != 307 and e.status != 308:
            raise
        redirected_url = urllib.parse.urljoin(url, e.headers["Location"])
        return http_get_json(redirected_url)


def generate_xmltv(output_directory):
    logging.info("Getting HDHomeRun Devices")
    try:
        devices = get_hdhr_devices()
    except:
        logging.exception("Error Getting HDHomeRun Devices")
    else:
        if devices:
            logging.info("Generating XMLTV")
            xml_root = ET.Element("tv")
            parsed_channels = []

            for device in devices:
                if "DeviceID" in device:
                    device_id = device["DeviceID"]
                    lineup_url = device["LineupURL"]
                    device_auth = device["DeviceAuth"]

                    logging.info(f"Processing Device: {device_id}")

                    logging.info("Getting HDHomeRun Lineup")
                    lineup = http_get_json(lineup_url)

                    logging.info("Saving HDHomeRun Lineup M3U")
                    urllib.request.urlretrieve(
                        lineup_url.replace("lineup.json", "lineup.m3u"),
                        os.path.join(output_directory, f"{device_id}.m3u"),
                    )

                    if lineup is not None:
                        logging.info(f"Lineup exists for device: {device_id}")
                        for channel in lineup:
                            channel_number = channel.get("GuideNumber")
                            if channel_number not in parsed_channels:
                                logging.info(
                                    f"Getting HDHomeRun channel guide for channel {channel_number}"
                                )
                                channel_guide = http_get_json(
                                    f"https://my.hdhomerun.com/api/guide.php?DeviceAuth={device_auth}&Channel={channel_number}"
                                )

                                channel_data = next(iter(channel_guide or []), None)
                                if channel_data is not None:
                                    parse_channel(xml_root, channel_data)
                                    guide_data = channel_data["Guide"]

                                    while guide_data is not None:
                                        last_end_time = 0

                                        for program in guide_data:
                                            last_end_time = parse_program(
                                                xml_root, program, channel_number
                                            )

                                        next_start_time = last_end_time + 1

                                        logging.info(
                                            f"Getting HDHomeRun channel guide for channel {channel_number} with start time {datetime.fromtimestamp(next_start_time)}"
                                        )
                                        channel_guide = http_get_json(
                                            f"https://my.hdhomerun.com/api/guide.php?DeviceAuth={device_auth}&Channel={channel_number}&Start={next_start_time}"
                                        )

                                        channel_data = next(iter(channel_guide or []), None)

                                        if channel_data is not None:
                                            guide_data = channel_data["Guide"]
                                        else:
                                            logging.info(
                                                f"No more guide for channel: {channel_number}"
                                            )
                                            guide_data = None
                                else:
                                    logging.info(f"No guide for channel: {channel_number}")
                                parsed_channels.append(channel_number)
                            else:
                                logging.info(f"Skipping channel: {channel_number}")
                    else:
                        logging.info(f"No lineup for device: {device_id}")
                else:
                    logging.info("No DeviceID")

            logging.info("Finished parsing information")
            output_file = os.path.join(output_directory, f"hdhr.xml")
            ET.ElementTree(xml_root).write(
                output_file, encoding="utf-8", xml_declaration=True
            )
            logging.info("Saved XMLTV")
        else:
            logging.warning("No HdHomeRun devices detected")


def main():

    parser = argparse.ArgumentParser(
        prog="hdhr2iptv",
        description="Generates M3U files and a XMLTV file for HDHomeRun devices",
        epilog="Thanks for using %(prog)s! :)",
    )

    parser.add_argument(
        "-l",
        "--log-file",
        type=argparse.FileType("w"),
        default=os.path.join(os.path.curdir, "hdhr2iptv.log"),
        help="output log filename",
    )

    parser.add_argument(
        "-s",
        "--run-daily-hour",
        type=int,
        help="will loop and run daily at this hour",
    )

    parser.add_argument(
        "-o",
        "--output-directory",
        type=directory,
        default=os.path.curdir,
        help="output directory for m3u and xml",
    )
    parser.add_argument("-v", "--version", action="version", version="%(prog)s 2.0.0")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(args.log_file.name, mode="w"),
            logging.StreamHandler(),
        ],
    )

    try:
        if args.run_daily_hour is None:
            generate_xmltv(args.output_directory)
        else:
            while True:
                generate_xmltv(args.output_directory)
                sleep_until_hour(args.run_daily_hour)
    except:
        logging.exception("Unhandled exception occurred.")


if __name__ == "__main__":
    sys.exit(main())
