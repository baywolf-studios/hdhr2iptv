import argparse
import datetime
import logging
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date, datetime, timezone
from logging.handlers import TimedRotatingFileHandler

from libhdhr import get_hdhr_devices
import utils


def parse_program(xml_root, program, channel_number):
    title = program["Title"]
    logging.info(f"Parsing Channel: {channel_number} Program: {title}")

    xml_program = ET.SubElement(xml_root, "programme", channel=channel_number)

    xml_program.set(
        "start", utils.convert_timestamp_to_xmltv_datetime(program["StartTime"])
    )

    xml_program.set(
        "stop", utils.convert_timestamp_to_xmltv_datetime(program["EndTime"])
    )

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


def get_hdhr_channel_guide(device_auth, channel_number, start_time=None):
    logging.info(f"Getting HDHomeRun Channel Guide for: {channel_number} {start_time}")
    url = f"https://my.hdhomerun.com/api/guide.php?DeviceAuth={device_auth}&Channel={channel_number}"
    if start_time is not None:
        url += f"&Start={start_time}"
    return utils.http_get_json_with_retry(url)


def get_cached_hdhr_channel_guide(
    cache_directory, device_auth, channel_number, start_time
):
    cache_filename = os.path.join(
        cache_directory, str(channel_number), str(start_time) + ".json"
    )

    if os.path.isfile(cache_filename):
        logging.info(
            f"Getting cached HDHomeRun Channel Guide for: {channel_number} {start_time}"
        )
        return utils.load_json_from_file(cache_filename)

    channel_guide = get_hdhr_channel_guide(device_auth, channel_number, start_time)
    channel_data = next(iter(channel_guide or []), None)
    if channel_data:
        logging.info(
            f"Caching HDHomeRun Channel Guide for: {channel_number} {start_time}"
        )
        utils.save_json_to_file(cache_filename, channel_guide)
    return channel_guide


def generate_m3u(output_directory, device_id, lineup):
    logging.info(f"Generating M3U for {device_id}")
    m3u_lines = ["#EXTM3U"]
    for channel in lineup:
        channel_number = channel.get("GuideNumber")
        channel_name = channel.get("GuideName")
        channel_url = channel.get("URL")
        channel_favorite = channel.get("Favorite")
        channel_hd = channel.get("HD")

        m3u_lines.append(
            f'#EXTINF:-1 channel-id="{channel_number}" channel-number="{channel_number}" tvg-id="{channel_number}" tvg-name="{channel_name}" tvg-chno="{channel_number}",{channel_name}'
        )
        if channel_favorite:
            m3u_lines.append("#EXTGRP:Favorites")
            if channel_hd:
                m3u_lines[-1] += ";HD"  # Append ";HD" to the previous line
        elif channel_hd:
            m3u_lines.append("#EXTGRP:HD")
        m3u_lines.append(channel_url)

    m3u_lines.append("")

    m3u_filename = os.path.join(output_directory, f"{device_id}.m3u")
    os.makedirs(os.path.dirname(m3u_filename), exist_ok=True)
    with open(m3u_filename, "w") as m3u_file:
        m3u_file.write("\r\n".join(m3u_lines))


def generate_xmltv(output_directory, cache_directory):
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
                    lineup = utils.http_get_json(lineup_url)

                    generate_m3u(output_directory, device_id, lineup)

                    if lineup is not None:
                        logging.info(f"Lineup exists for device: {device_id}")
                        for channel in lineup:
                            channel_number = channel.get("GuideNumber")
                            if channel_number not in parsed_channels:
                                channel_guide = get_hdhr_channel_guide(
                                    device_auth, channel_number
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
                                        channel_guide = get_cached_hdhr_channel_guide(
                                            cache_directory,
                                            device_auth,
                                            channel_number,
                                            next_start_time,
                                        )
                                        channel_data = next(
                                            iter(channel_guide or []), None
                                        )

                                        if channel_data is not None:
                                            guide_data = channel_data["Guide"]
                                        else:
                                            logging.info(
                                                f"No more guide for channel: {channel_number}"
                                            )
                                            guide_data = None
                                else:
                                    logging.info(
                                        f"No guide for channel: {channel_number}"
                                    )
                                parsed_channels.append(channel_number)
                            else:
                                logging.info(f"Skipping channel: {channel_number}")
                    else:
                        logging.info(f"No lineup for device: {device_id}")
                else:
                    logging.info("No DeviceID")

            logging.info("Finished parsing information")
            xmltv_filename = os.path.join(output_directory, f"hdhr.xml")
            os.makedirs(os.path.dirname(xmltv_filename), exist_ok=True)
            ET.ElementTree(xml_root).write(
                xmltv_filename, encoding="utf-8", xml_declaration=True
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
        default=os.path.join(os.path.curdir, "output", "hdhr2iptv.log"),
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
        type=utils.directory,
        default=os.path.join(os.path.curdir, "output"),
        help="output directory for m3u and xml",
    )

    parser.add_argument(
        "-c",
        "--cache-directory",
        type=utils.directory,
        default=os.path.join(os.path.curdir, "cache"),
        help="cache directory for json",
    )
    parser.add_argument("-v", "--version", action="version", version="%(prog)s 2.0.0")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            TimedRotatingFileHandler(args.log_file.name, when="D"),
            logging.StreamHandler(),
        ],
    )

    if args.run_daily_hour is None:
        generate_xmltv(args.output_directory, args.cache_directory)
        utils.delete_files_created_30_days_ago(args.cache_directory)
    else:
        while True:
            utils.sleep_until_hour(args.run_daily_hour)
            try:
                generate_xmltv(args.output_directory, args.cache_directory)
                utils.delete_files_created_30_days_ago(args.cache_directory)
            except:
                logging.exception("Unhandled exception occurred.")


if __name__ == "__main__":
    sys.exit(main())
