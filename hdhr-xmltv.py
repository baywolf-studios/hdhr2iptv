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
    is_behind_utc = False

    # If the current time is behind UTC convert the offset
    # seconds to a positive value and set the flag variable.
    if utc_offset_secs < 0:
        is_behind_utc = True
        utc_offset_secs *= -1

    # Build a UTC offset string suitable for use in a timestamp.

    if is_behind_utc:
        pos_neg_prefix = "-"
    else:
        pos_neg_prefix = "+"

    utc_offset = time.gmtime(utc_offset_secs)
    utc_offset_fmt = time.strftime("%H:%M", utc_offset)
    utc_offset_str = pos_neg_prefix + utc_offset_fmt

    return utc_offset_str


def process_program(xml, program, guideName):
    logging.info("Processing Show: " + program["Title"])

    timezone_offset = get_utc_offset_str().replace(":", "")
    # program
    # Create the "programme" element and set the Channel attribute to "GuideName" from json
    xmlProgram = ET.SubElement(xml, "programme", channel=guideName)
    # 	 channel=channel['GuideName'])

    # set the start date and time from the feed
    xmlProgram.set(
        "start",
        datetime.fromtimestamp(program["StartTime"]).strftime("%Y%m%d%H%M%S") +
        " " + timezone_offset,
    )

    # set the end date and time from the feed
    xmlProgram.set(
        "stop",
        datetime.fromtimestamp(program["EndTime"]).strftime("%Y%m%d%H%M%S") +
        " " + timezone_offset,
    )

    # Title
    ET.SubElement(xmlProgram, "title", lang="en").text = program["Title"]

    # Sub Title
    if "EpisodeTitle" in program:
        ET.SubElement(xmlProgram, "sub-title",
                      lang="en").text = program["EpisodeTitle"]

    # Description
    if "Synopsis" in program:
        ET.SubElement(xmlProgram, "desc").text = program["Synopsis"]

    # Credits
    # We add a blank entry to satisfy Plex
    ET.SubElement(xmlProgram, "credits").text = ""

    addedEpisode = False

    if "EpisodeNumber" in program:
        # add the friendly display
        ET.SubElement(xmlProgram, "episode-num",
                      system="onscreen").text = program["EpisodeNumber"]
        # Fake the xml version
        en = program["EpisodeNumber"]
        parts = en.split("E")
        season = parts[0].replace("S", "")
        episode = parts[1]
        # Assign the fake xml version
        ET.SubElement(xmlProgram, "episode-num",
                      system="xmltv_ns").text = (season + " . " + episode +
                                                 " . 0/1")
        # set the category flag to series
        ET.SubElement(xmlProgram, "category", lang="en").text = "series"
        addedEpisode = True

    if "OriginalAirdate" in program:
        if program["OriginalAirdate"] > 0:
            # The 86400 is because the HdHomeRun feed is off by a day, this fixes that.
            ET.SubElement(
                xmlProgram,
                "previously-shown",
                start=datetime.fromtimestamp(program["OriginalAirdate"] +
                                             86400).strftime("%Y%m%d%H%M%S") +
                " " + timezone_offset,
            )

    if "ImageURL" in program:
        ET.SubElement(xmlProgram, "icon", src=program["ImageURL"])

    xmlAudio = ET.SubElement(xmlProgram, "audio")
    ET.SubElement(xmlAudio, "stereo").text = "stereo"
    ET.SubElement(xmlProgram, "subtitles", type="teletext")

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
            ET.SubElement(xmlProgram, "category", lang="en").text = "series"
            # create a fake episode number for it
            ET.SubElement(xmlProgram, "episode-num",
                          system="xmltv_ns").text = date_time_to_episode()
            ET.SubElement(
                xmlProgram, "episode-num",
                system="onscreen").text = date_time_to_episode_friendly()
            addedEpisode = True

        for filter in program["Filter"]:
            # Lowercase the filter... apearenttly Plex is case sensitive
            filterstringLower = str(filter).lower()
            # add the filter as a category
            ET.SubElement(xmlProgram, "category",
                          lang="en").text = filterstringLower
            # If the filter is news or sports...
            # if (filterstringLower == "news" or filterstringLower == "sports"):
            # 	#And the show didn't have it's own episode number...
            # 	if ( addedEpisode == False ):
            # 		#logging.info("-------> Creating Fake Season and Episode for News or Sports show.")
            # 		#add a category for series
            # 		ET.SubElement(xmlProgram, "category",lang="en").text = "series"
            # 		#create a fake episode number for it
            # 		ET.SubElement(xmlProgram, "episode-num", system="xmltv_ns").text = date_time_to_episode()
            # 		ET.SubElement(xmlProgram, "episode-num", system="onscreen").text = date_time_to_episode_friendly()

    # Return the endtime so we know where to start from on next loop.
    return program["EndTime"]


def process_channel(xml, data, deviceAuth):
    logging.info("Processing Channel: " + data.get("GuideNumber") + " " +
                 data.get("GuideName"))

    # channel
    xmlChannel = ET.SubElement(xml, "channel", id=data.get("GuideName"))

    # display name
    ET.SubElement(xmlChannel, "display-name").text = data.get("GuideName")

    # display name
    ET.SubElement(xmlChannel, "display-name").text = data.get("GuideNumber")

    # display name
    if "Affiliate" in data:
        ET.SubElement(xmlChannel, "display-name").text = data.get("Affiliate")

    if "ImageURL" in data:
        ET.SubElement(xmlChannel, "icon", src=data.get("ImageURL"))

    maxTime = 0

    for program in data.get("Guide"):
        maxTime = process_program(xml, program, data.get("GuideName"))

    maxTime = maxTime + 1
    counter = 0

    # The first pull is for 4 hours, each of these are 8 hours
    # So if we do this 21 times we will have fetched the complete week
    try:
        while counter < 24:
            chanData = get_hdhr_connect_channel_programs(
                deviceAuth, data.get("GuideNumber"), maxTime)
            for chan in chanData:
                for program in chan["Guide"]:
                    maxTime = process_program(xml, program,
                                              data.get("GuideName"))
            counter = counter + 1

    except:
        logging.info("It appears you do not have the HdHomeRunDvr Service.")


def save_string_to_file(strData, filename):
    with open(filename, "wb") as outfile:
        outfile.write(strData)


def load_json_from_file(filename):
    return json.load(open(filename))


def save_json_to_file(data, filename):
    with open(filename, "w") as outfile:
        json.dump(data, outfile, indent=4)


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


def get_hdhr_connect_devices():
    logging.info("Getting Connected Devices.")
    return http_get_json("https://my.hdhomerun.com/discover")


def get_hdhr_connect_discover(discover_url):
    logging.info("Discovering...")
    data = http_get_json(discover_url)
    device_auth = data["DeviceAuth"]
    return device_auth


def get_hdhr_connect_discover_line_up_url(discover_url):
    logging.info("Getting Lineup Url")
    data = http_get_json(discover_url)
    LineupURL = data["LineupURL"]
    return LineupURL


def get_hdhr_connect_line_up(lineupUrl):
    logging.info("Getting Lineup")
    return http_get_json(lineupUrl)


def get_hdhr_connect_channels(device_auth):
    logging.info("Getting Channels.")
    return http_get_json(
        "https://my.hdhomerun.com/api/guide.php?DeviceAuth=%s" % device_auth)


def get_hdhr_connect_channel_programs(device_auth, guideNumber, timeStamp):
    logging.info("Getting Extended Programs")
    return http_get_json("https://my.hdhomerun.com/api/guide.php?DeviceAuth=" +
                         device_auth + "&Channel=" + guideNumber + "&Start=" +
                         str(timeStamp) + "&SynopsisLength=160")


def in_list(l, value):
    if l.count(value) > 0:
        return True
    else:
        return False
    return False


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


def main():

    parser = argparse.ArgumentParser(
        prog="hdhr-xmltv",
        description="Generates a XMLTV file for HDHomeRun devices",
        epilog="Thanks for using %(prog)s! :)",
    )

    parser.add_argument("-o",
                        "--output-file",
                        type=argparse.FileType('w'),
                        default="hdhomerun.xml")
    parser.add_argument("-v",
                        "--version",
                        action="version",
                        version="%(prog)s 0.1.0")

    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        handlers=[
                            logging.FileHandler("hdhr-xmltv.log", mode='w'),
                            logging.StreamHandler()
                        ])

    print("Downloading Content...  Please wait.")
    print("Check the log for progress.")
    logging.info("Starting...")

    xml = ET.Element("tv")

    try:
        devices = get_hdhr_connect_devices()
    except:
        logging.exception("No HdHomeRun devices detected.")
        exit()

    for device in devices:
        if "DeviceID" in device:
            logging.info("Processing Device: " + device["DeviceID"])

            deviceAuth = get_hdhr_connect_discover(device["DiscoverURL"])

            lineUpUrl = get_hdhr_connect_discover_line_up_url(
                device["DiscoverURL"])

            LineUp = get_hdhr_connect_line_up(lineUpUrl)

            if len(LineUp) > 0:
                logging.info("Line Up Exists for device")
                channels = get_hdhr_connect_channels(deviceAuth)
                for chan in channels:
                    process_channel(xml, chan, deviceAuth)
            else:
                logging.info("No Lineup for device!")
        else:
            logging.info("Must be storage...")

    reformed_xml = minidom.parseString(ET.tostring(xml))
    xmltv = reformed_xml.toprettyxml(encoding="utf-8")
    logging.info("Finished compiling information.  Saving...")
    if os.path.exists(args.output_file.name):
        os.remove(args.output_file.name)
    save_string_to_file(xmltv, args.output_file.name)
    logging.info("Finished.")


if __name__ == "__main__":
    main()
