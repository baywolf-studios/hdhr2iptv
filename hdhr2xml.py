import argparse
import datetime
import json
import logging
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone

LOCAL_TIMEZONE = datetime.now(timezone.utc).astimezone().tzinfo


def timestamp_to_xmltv_datetime(timestamp):
    return datetime.fromtimestamp(
        timestamp, tz=LOCAL_TIMEZONE).strftime("%Y%m%d%H%M%S %z")


def parse_program(xml_root, program, channel_number):
    title = program["Title"]
    logging.info(f"Parsing Channel: {channel_number} Program: {title}")

    xml_program = ET.SubElement(xml_root, "programme", channel=channel_number)

    xml_program.set("start", timestamp_to_xmltv_datetime(program["StartTime"]))

    xml_program.set("stop", timestamp_to_xmltv_datetime(program["EndTime"]))

    ET.SubElement(xml_program, "title", lang="en").text = title

    if "EpisodeTitle" in program:
        ET.SubElement(xml_program, "sub-title",
                      lang="en").text = program["EpisodeTitle"]

    if "Synopsis" in program:
        ET.SubElement(xml_program, "desc").text = program["Synopsis"]

    # Add a blank credits to satisfy Plex
    ET.SubElement(xml_program, "credits").text = ""

    if "EpisodeNumber" in program:
        # Fake the xml version
        season = str(
            int(program["EpisodeNumber"].split('S')[1].split('E')[0]) - 1)
        episode = str(
            int(program["EpisodeNumber"].split('S')[1].split('E')[1]) - 1)
        ET.SubElement(xml_program, "episode-num",
                      system="xmltv_ns").text = (season + "." + episode + ".")

        ET.SubElement(xml_program, "episode-num",
                      system="onscreen").text = program["EpisodeNumber"]

        ET.SubElement(xml_program, "episode-num",
                      system="SxxExx").text = program["EpisodeNumber"]

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
                ET.SubElement(xml_program, "category",
                              lang="en").text = "Movie"
                is_movie = True

    if not is_movie:
        if "OriginalAirdate" in program:
            original_air_date = datetime.utcfromtimestamp(
                program["OriginalAirdate"]).date()
            current_air_date = datetime.fromtimestamp(
                program["StartTime"]).date()
            if original_air_date < current_air_date:
                ET.SubElement(xml_program, "previously-shown")
                ET.SubElement(xml_program, "previously-aired")
            else:
                ET.SubElement(
                    xml_program,
                    "new",
                )
            ET.SubElement(
                xml_program, "episode-num",
                system="original_air_date").text = str(original_air_date)
        else:
            ET.SubElement(
                xml_program,
                "new",
            )
            ET.SubElement(xml_program,
                          "episode-num",
                          system="original_air_date").text = str(date.today())

    # Return the endtime so we know where to start from on next loop.
    return program["EndTime"]


def parse_channel(xml_root, channel):
    channel_number = channel.get("GuideNumber")

    logging.info(f"Parsing Channel: {channel_number}")

    xml_channel = ET.SubElement(xml_root, "channel", id=channel_number)

    ET.SubElement(xml_channel, "display-name").text = channel_number

    ET.SubElement(xml_channel, "display-name").text = channel.get("GuideName")

    if "Affiliate" in channel:
        ET.SubElement(xml_channel,
                      "display-name").text = channel.get("Affiliate")

    if "ImageURL" in channel:
        ET.SubElement(xml_channel, "icon", src=channel.get("ImageURL"))

    return xml_channel


def http_get_json(url):
    try:
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read().decode(r.info().get_param("charset")
                                              or "utf-8"))
            return data
    except urllib.error.HTTPError as e:
        if e.status != 307 and e.status != 308:
            raise
        redirected_url = urllib.parse.urljoin(url, e.headers["Location"])
        return http_get_json(redirected_url)


def get_hdhr_channel_guide(device_auth, channel_number, start_time=None):
    logging.info(f"Getting HDHomeRun Channel Guide for: {channel_number}")
    url = "https://my.hdhomerun.com/api/guide.php?DeviceAuth=" + device_auth + "&Channel=" + channel_number
    if start_time is not None:
        url = url + "&Start=" + str(start_time)
    return http_get_json(url)


def get_hdhr_lineup(lineupUrl):
    logging.info("Getting HDHomeRun Lineup")
    return http_get_json(lineupUrl)


def get_hdhr_device_auth(discover_url):
    logging.info("Getting HDHomeRun Device Auth")
    data = http_get_json(discover_url)
    device_auth = data["DeviceAuth"]
    return device_auth


def get_hdhr_devices():
    logging.info("Getting HDHomeRun Devices")
    return http_get_json("https://my.hdhomerun.com/discover")


def generate_xmltv(output_file, favorites_only):
    logging.info("Generating XMLTV")
    xml_root = ET.Element("tv")

    devices = get_hdhr_devices()

    if devices is not None:
        parsed_channels = []

        for device in devices:
            if "DeviceID" in device:
                device_id = device["DeviceID"]
                discover_url = device["DiscoverURL"]
                lineup_url = device["LineupURL"]

                logging.info(f"Processing Device: {device_id}")

                device_auth = get_hdhr_device_auth(discover_url)

                lineup = get_hdhr_lineup(lineup_url)

                if lineup is not None:
                    logging.info(f"Lineup exists for device: {device_id}")
                    for channel in lineup:
                        channel_number = channel.get("GuideNumber")
                        channel_favorite = ("Favorite" in channel) and (
                            channel["Favorite"])
                        if (channel_number not in parsed_channels) and (
                                not favorites_only or channel_favorite):

                            channel_guide = get_hdhr_channel_guide(
                                device_auth, channel_number)

                            channel_data = next(iter(channel_guide or []),
                                                None)
                            if channel_data is not None:
                                parse_channel(xml_root, channel_data)
                                guide_data = channel_data["Guide"]

                                while guide_data is not None:
                                    last_end_time = 0

                                    for program in guide_data:
                                        last_end_time = parse_program(
                                            xml_root, program, channel_number)

                                    next_start_time = last_end_time + 1

                                    channel_guide = get_hdhr_channel_guide(
                                        device_auth, channel_number,
                                        next_start_time)

                                    channel_data = next(
                                        iter(channel_guide or []), None)

                                    if channel_data is not None:
                                        guide_data = channel_data["Guide"]
                                    else:
                                        logging.info(
                                            f"No more guide for channel: {channel_number}"
                                        )
                                        guide_data = None
                            else:
                                logging.info(
                                    f"No guide for channel: {channel_number}")
                            parsed_channels.append(channel_number)
                        else:
                            logging.info(f"Skipping channel: " +
                                         channel_number)
                else:
                    logging.info(f"No lineup for device: {device_id}")
            else:
                logging.info("No DeviceID")

        logging.info("Finished parsing information")
        ET.ElementTree(xml_root).write(output_file,
                                       encoding='utf-8',
                                       xml_declaration=True)
        logging.info("Saved XMLTV")
    else:
        logging.warning("No HdHomeRun devices detected")


def main():

    parser = argparse.ArgumentParser(
        prog="hdhr2xml",
        description="Generates a XMLTV file for HDHomeRun devices",
        epilog="Thanks for using %(prog)s! :)",
    )

    parser.add_argument("-l",
                        "--log-file",
                        type=argparse.FileType('w'),
                        default="hdhr2xml.log",
                        help="output log filename")
    parser.add_argument("-o",
                        "--output-file",
                        type=argparse.FileType('w'),
                        default="xmltv.xml",
                        help="output xml filename")
    parser.add_argument("-s",
                        "--sleep-time",
                        type=int,
                        help="number of seconds to sleep before looping")
    parser.add_argument("-f",
                        "--favorites-only",
                        action='store_true',
                        help="only retrieve epg for favorite channels")
    parser.add_argument("-v",
                        "--version",
                        action="version",
                        version="%(prog)s 0.1.0")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[
                            logging.FileHandler(args.log_file.name, mode='w'),
                            logging.StreamHandler()
                        ])

    try:
        if args.sleep_time is None:
            generate_xmltv(args.output_file.name, args.favorites_only)
        else:
            while True:
                generate_xmltv(args.output_file.name, args.favorites_only)
                logging.info(f"Sleeping for {args.sleep_time} seconds")
                time.sleep(args.sleep_time)
    except:
        logging.exception("Unhandled exception occurred.")


if __name__ == '__main__':
    sys.exit(main())
