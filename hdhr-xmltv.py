import argparse
import sys
import json
import logging
import datetime
import subprocess
import time
import os
import urllib.request
import xml.etree.cElementTree as ET
from datetime import datetime
from xml.dom import minidom
from pprint import pprint


def get_utc_offset_str():
    """
    Returns a UTC offset string of the current time suitable for use in the
    most widely used timestamps (i.e. ISO 8601, RFC 3339). For example:
    10 hours ahead, 5 hours behind, and time is UTC: +10:00, -05:00, +00:00
    """

    # Calculate the UTC time difference in seconds.
    timestamp = time.time()
    time_now = datetime.fromtimestamp(timestamp)
    time_utc = datetime.utcfromtimestamp(timestamp)
    utc_offset_secs = (time_now - time_utc).total_seconds()

    # Flag variable to hold if the current time is behind UTC.
    is_behind_utc = utc_offset_secs < 0

    # If the current time is behind UTC convert the offset
    # seconds to a positive value and set the flag variable.
    if is_behind_utc:
        utc_offset_secs *= -1
        pos_neg_prefix = "-"
    else:
        pos_neg_prefix = "+"

    utc_offset = time.gmtime(utc_offset_secs)
    utc_offset_fmt = time.strftime("%H%M", utc_offset)
    utc_offset_str = pos_neg_prefix + utc_offset_fmt

    return utc_offset_str


def parse_channel(xml_root, channel):
    channel_number = channel.get("GuideNumber")

    logging.info(f"Parsing Channel: {channel_number}")

    # channel
    xml_channel = ET.SubElement(xml_root, "channel", id=channel_number)

    # display name
    ET.SubElement(xml_channel, "display-name").text = channel_number

    # display name
    ET.SubElement(xml_channel, "display-name").text = channel.get("GuideName")

    if "Affiliate" in channel:
        ET.SubElement(xml_channel,
                      "display-name").text = channel.get("Affiliate")

    if "ImageURL" in channel:
        ET.SubElement(xml_channel, "icon", src=channel.get("ImageURL"))

    return xml_channel


def parse_program(xml_root, program, channel_number):
    title = program["Title"]
    logging.info(f"Parsing Channel: {channel_number} Program: {title}")

    timezone_offset = get_utc_offset_str()

    # Create the "programme" element and set the Channel attribute to "GuideName" from json
    xml_program = ET.SubElement(xml_root, "programme", channel=channel_number)

    # set the start date and time from the feed
    xml_program.set(
        "start",
        datetime.fromtimestamp(program["StartTime"]).strftime("%Y%m%d%H%M%S") +
        " " + timezone_offset,
    )

    # set the end date and time from the feed
    xml_program.set(
        "stop",
        datetime.fromtimestamp(program["EndTime"]).strftime("%Y%m%d%H%M%S") +
        " " + timezone_offset,
    )

    # Title
    ET.SubElement(xml_program, "title", lang="en").text = title

    # Sub Title
    if "EpisodeTitle" in program:
        ET.SubElement(xml_program, "sub-title",
                      lang="en").text = program["EpisodeTitle"]

    # Description
    if "Synopsis" in program:
        ET.SubElement(xml_program, "desc").text = program["Synopsis"]

    # Credits
    # We add a blank entry to satisfy Plex
    ET.SubElement(xml_program, "credits").text = ""

    addedEpisode = False

    if "EpisodeNumber" in program:
        # add the friendly display
        ET.SubElement(xml_program, "episode-num",
                      system="onscreen").text = program["EpisodeNumber"]
        # Fake the xml version
        en = program["EpisodeNumber"]
        parts = en.split("E")
        season = int(parts[0].replace("S", "")) - 1
        episode = int(parts[1]) - 1
        # Assign the fake xml version
        ET.SubElement(xml_program, "episode-num",
                      system="xmltv_ns").text = (str(season) + " . " +
                                                 str(episode) + " . 0/1")
        # set the category flag to series
        ET.SubElement(xml_program, "category", lang="en").text = "series"
        addedEpisode = True

    if "OriginalAirdate" in program:
        if program["OriginalAirdate"] > 0:
            # The 86400 is because the HdHomeRun feed is off by a day, this fixes that.
            ET.SubElement(
                xml_program,
                "previously-shown",
                start=datetime.fromtimestamp(program["OriginalAirdate"] +
                                             86400).strftime("%Y%m%d%H%M%S") +
                " " + timezone_offset,
            )

    if "ImageURL" in program:
        ET.SubElement(xml_program, "icon", src=program["ImageURL"])

    xmlAudio = ET.SubElement(xml_program, "audio")
    ET.SubElement(xmlAudio, "stereo").text = "stereo"
    ET.SubElement(xml_program, "subtitles", type="teletext")

    if "Filter" in program:
        # Search the filters and see if it is a movie
        FoundMovieCategory = False
        for filter in program["Filter"]:
            filterstringLower = str(filter).lower()
            if filterstringLower == "movies":
                FoundMovieCategory = True
                break

        # If we didn't find the movie category, and we haven't added an episode flag, lets do it!
        if FoundMovieCategory == False and addedEpisode == False:
            ET.SubElement(xml_program, "category", lang="en").text = "series"
            # create a fake episode number for it
            ET.SubElement(xml_program, "episode-num",
                          system="xmltv_ns").text = date_time_to_episode()
            ET.SubElement(
                xml_program, "episode-num",
                system="onscreen").text = date_time_to_episode_friendly()
            addedEpisode = True

        for filter in program["Filter"]:
            # Lowercase the filter... apearenttly Plex is case sensitive
            filterstringLower = str(filter).lower()
            # add the filter as a category
            ET.SubElement(xml_program, "category",
                          lang="en").text = filterstringLower
            # If the filter is news or sports...
            # if (filterstringLower == "news" or filterstringLower == "sports"):
            # 	#And the show didn't have it's own episode number...
            # 	if ( addedEpisode == False ):
            # 		#logging.info("-------> Creating Fake Season and Episode for News or Sports show.")
            # 		#add a category for series
            # 		ET.SubElement(xml_program, "category",lang="en").text = "series"
            # 		#create a fake episode number for it
            # 		ET.SubElement(xml_program, "episode-num", system="xmltv_ns").text = date_time_to_episode()
            # 		ET.SubElement(xml_program, "episode-num", system="onscreen").text = date_time_to_episode_friendly()

    # Return the endtime so we know where to start from on next loop.
    return program["EndTime"]


def save_string_to_file(strData, filename):
    with open(filename, "wb") as outfile:
        outfile.write(strData)


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


def get_hdhr_devices():
    logging.info("Getting Connected Devices.")
    return http_get_json("https://my.hdhomerun.com/discover")


def get_hdhr_device_auth(discover_url):
    logging.info("Discovering...")
    data = http_get_json(discover_url)
    device_auth = data["DeviceAuth"]
    return device_auth


def get_hdhr_lineup(lineupUrl):
    logging.info("Getting Lineup")
    return http_get_json(lineupUrl)


def get_hdhr_channel_guide(device_auth, channel_number, start_time=None):
    logging.info("Getting Channel Guide")
    url = "https://my.hdhomerun.com/api/guide.php?DeviceAuth=" + device_auth + "&Channel=" + channel_number
    if start_time is not None:
        url = url + "&Start=" + str(start_time)
    return http_get_json(url)


def date_time_to_episode():
    timestamp = time.time()
    time_now = datetime.fromtimestamp(timestamp)
    season = time_now.strftime("%Y")
    episode = time_now.strftime("%m%d%H")
    return season + " . " + episode + " . 0/1"


def date_time_to_episode_friendly():
    timestamp = time.time()
    time_now = datetime.fromtimestamp(timestamp)
    season = time_now.strftime("%Y")
    episode = time_now.strftime("%m%d%H")
    return "S" + season + "E" + episode


def generate_xmltv(output_file):
    logging.info("Generating XMLTV.")
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
                        if channel_number not in parsed_channels:
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

        reformed_xml = minidom.parseString(ET.tostring(xml_root))
        xmltv = reformed_xml.toprettyxml(encoding="utf-8")
        logging.info("Finished parsing information")
        save_string_to_file(xmltv, output_file)
        logging.info("Saved XMLTV")
    else:
        logging.warning("No HdHomeRun devices detected")


def main():

    parser = argparse.ArgumentParser(
        prog="hdhr-xmltv",
        description="Generates a XMLTV file for HDHomeRun devices",
        epilog="Thanks for using %(prog)s! :)",
    )

    parser.add_argument("-l",
                        "--log-file",
                        type=argparse.FileType('w'),
                        default="hdhr-xmltv.log")
    parser.add_argument("-o",
                        "--output-file",
                        type=argparse.FileType('w'),
                        default="xmltv.xml")
    parser.add_argument("-s", "--sleep-time", type=int)
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
            generate_xmltv(args.output_file.name)
        else:
            while True:
                generate_xmltv(args.output_file.name)
                logging.info(f"Sleeping for {args.sleep_time} seconds")
                sleep(args.sleep_time)
    except:
        logging.exception("Unhandled exception occurred.")


if __name__ == "__main__":
    main()
