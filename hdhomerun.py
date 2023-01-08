import sys
import json
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


def ProcessProgram(xml, program, guideName):

    WriteLog("Processing Show: " + program["Title"])

    timezone_offset = get_utc_offset_str().replace(":", "")
    # program
    # Create the "programme" element and set the Channel attribute to "GuideName" from json
    xmlProgram = ET.SubElement(xml, "programme", channel=guideName)
    # 	 channel=channel['GuideName'])

    # set the start date and time from the feed
    xmlProgram.set(
        "start",
        datetime.fromtimestamp(program["StartTime"]).strftime("%Y%m%d%H%M%S")
        + " "
        + timezone_offset,
    )

    # set the end date and time from the feed
    xmlProgram.set(
        "stop",
        datetime.fromtimestamp(program["EndTime"]).strftime("%Y%m%d%H%M%S")
        + " "
        + timezone_offset,
    )

    # Title
    ET.SubElement(xmlProgram, "title", lang="en").text = program["Title"]

    # Sub Title
    if "EpisodeTitle" in program:
        ET.SubElement(xmlProgram, "sub-title", lang="en").text = program["EpisodeTitle"]

    # Description
    if "Synopsis" in program:
        ET.SubElement(xmlProgram, "desc").text = program["Synopsis"]

    # Credits
    # We add a blank entry to satisfy Plex
    ET.SubElement(xmlProgram, "credits").text = ""

    addedEpisode = False

    if "EpisodeNumber" in program:
        # add the friendly display
        ET.SubElement(xmlProgram, "episode-num", system="onscreen").text = program[
            "EpisodeNumber"
        ]
        # Fake the xml version
        en = program["EpisodeNumber"]
        parts = en.split("E")
        season = parts[0].replace("S", "")
        episode = parts[1]
        # Assign the fake xml version
        ET.SubElement(xmlProgram, "episode-num", system="xmltv_ns").text = (
            season + " . " + episode + " . 0/1"
        )
        # set the category flag to series
        ET.SubElement(xmlProgram, "category", lang="en").text = "series"
        addedEpisode = True

    if "OriginalAirdate" in program:
        if program["OriginalAirdate"] > 0:
            # The 86400 is because the HdHomeRun feed is off by a day, this fixes that.
            ET.SubElement(
                xmlProgram,
                "previously-shown",
                start=datetime.fromtimestamp(
                    program["OriginalAirdate"] + 86400
                ).strftime("%Y%m%d%H%M%S")
                + " "
                + timezone_offset,
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
            ET.SubElement(
                xmlProgram, "episode-num", system="xmltv_ns"
            ).text = DateTimeToEpisode()
            ET.SubElement(
                xmlProgram, "episode-num", system="onscreen"
            ).text = DateTimeToEpisodeFriendly()
            addedEpisode = True

        for filter in program["Filter"]:
            # Lowercase the filter... apearenttly Plex is case sensitive
            filterstringLower = str(filter).lower()
            # add the filter as a category
            ET.SubElement(xmlProgram, "category", lang="en").text = filterstringLower
            # If the filter is news or sports...
            # if (filterstringLower == "news" or filterstringLower == "sports"):
            # 	#And the show didn't have it's own episode number...
            # 	if ( addedEpisode == False ):
            # 		#WriteLog("-------> Creating Fake Season and Episode for News or Sports show.")
            # 		#add a category for series
            # 		ET.SubElement(xmlProgram, "category",lang="en").text = "series"
            # 		#create a fake episode number for it
            # 		ET.SubElement(xmlProgram, "episode-num", system="xmltv_ns").text = DateTimeToEpisode()
            # 		ET.SubElement(xmlProgram, "episode-num", system="onscreen").text = DateTimeToEpisodeFriendly()

    # Return the endtime so we know where to start from on next loop.
    return program["EndTime"]


def processChannel(xml, data, deviceAuth):

    WriteLog(
        "Processing Channel: " + data.get("GuideNumber") + " " + data.get("GuideName")
    )

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
        maxTime = ProcessProgram(xml, program, data.get("GuideName"))

    maxTime = maxTime + 1
    counter = 0

    # The first pull is for 4 hours, each of these are 8 hours
    # So if we do this 21 times we will have fetched the complete week
    try:
        while counter < 24:
            chanData = GetHdConnectChannelPrograms(
                deviceAuth, data.get("GuideNumber"), maxTime
            )
            for chan in chanData:
                for program in chan["Guide"]:
                    maxTime = ProcessProgram(xml, program, data.get("GuideName"))
            counter = counter + 1

    except:
        WriteLog("It appears you do not have the HdHomeRunDvr Service.")


def saveStringToFile(strData, filename):
    with open(filename, "wb") as outfile:
        outfile.write(strData)


def loadJsonFromFile(filename):
    return json.load(open(filename))


def saveJsonToFile(data, filename):
    with open(filename, "w") as outfile:
        json.dump(data, outfile, indent=4)


def get(url):
    try:
        with urllib.request.urlopen(url) as r:
            data = json.loads(r.read().decode(r.info().get_param("charset") or "utf-8"))
            return data
    except urllib.error.HTTPError as e:
        if e.status != 307 and e.status != 308:
            raise
        redirected_url = urllib.parse.urljoin(url, e.headers["Location"])
        return get(redirected_url)


def GetHdConnectDevices():
    WriteLog("Getting Connected Devices.")
    return get("https://my.hdhomerun.com/discover")


def GetHdConnectDiscover(discover_url):
    WriteLog("Discovering...")
    data = get(discover_url)
    device_auth = data["DeviceAuth"]
    return device_auth


def GetHdConnectDiscoverLineUpUrl(discover_url):
    WriteLog("Getting Lineup Url")
    data = get(discover_url)
    LineupURL = data["LineupURL"]
    return LineupURL


def GetHdConnectLineUp(lineupUrl):
    WriteLog("Getting Lineup")
    return get(lineupUrl)


def GetHdConnectChannels(device_auth):
    WriteLog("Getting Channels.")
    return get("https://my.hdhomerun.com/api/guide.php?DeviceAuth=%s" % device_auth)


def GetHdConnectChannelPrograms(device_auth, guideNumber, timeStamp):
    WriteLog("Getting Extended Programs")
    return get(
        "https://my.hdhomerun.com/api/guide.php?DeviceAuth="
        + device_auth
        + "&Channel="
        + guideNumber
        + "&Start="
        + str(timeStamp)
        + "&SynopsisLength=160"
    )


def InList(l, value):
    if l.count(value) > 0:
        return True
    else:
        return False
    return False


def ClearLog():
    if os.path.exists("HdHomerun.log"):
        os.remove("HdHomerun.log")
    if os.path.exists("hdhomerun.xml"):
        os.remove("hdhomerun.xml")


def DateTimeToEpisode():
    timestamp = time.time()
    time_now = datetime.fromtimestamp(timestamp)
    season = time_now.strftime("%Y")
    episode = time_now.strftime("%m%d%H")
    return season + " . " + episode + " . 0/1"


def DateTimeToEpisodeFriendly():
    timestamp = time.time()
    time_now = datetime.fromtimestamp(timestamp)
    season = time_now.strftime("%Y")
    episode = time_now.strftime("%m%d%H")
    return "S" + season + "E" + episode


def WriteLog(message):
    timestamp = time.time()
    time_now = datetime.fromtimestamp(timestamp)
    timeString = time_now.strftime("%Y%m%d%H%M%S")

    with open("HdHomerun.log", "ab") as logfile:
        output = str(timeString) + " " + str(message) + "\n"
        logfile.write(output.encode("utf-8"))
    print(output.encode("utf-8"))


def main():
    ClearLog()
    print("Downloading Content...  Please wait.")
    print("Check the log for progress.")
    WriteLog("Starting...")

    xml = ET.Element("tv")

    try:
        devices = GetHdConnectDevices()
    except:
        WriteLog("No HdHomeRun devices detected.")
        exit()

    processedChannelList = ["empty", "empty"]

    for device in devices:

        if "DeviceID" in device:

            WriteLog("Processing Device: " + device["DeviceID"])

            deviceAuth = GetHdConnectDiscover(device["DiscoverURL"])

            lineUpUrl = GetHdConnectDiscoverLineUpUrl(device["DiscoverURL"])

            LineUp = GetHdConnectLineUp(lineUpUrl)

            if len(LineUp) > 0:
                WriteLog("Line Up Exists for device")
                channels = GetHdConnectChannels(deviceAuth)
                for chan in channels:
                    ch = str(chan.get("GuideNumber"))
                    if InList(processedChannelList, ch) == False:
                        WriteLog("Processing Channel: " + ch)
                        processedChannelList.append(ch)
                        processChannel(xml, chan, deviceAuth)
                    else:
                        WriteLog("Skipping Channel " + ch + ", already processed.")
            else:
                WriteLog("No Lineup for device!")
        else:
            WriteLog("Must be storage...")

    reformed_xml = minidom.parseString(ET.tostring(xml))
    xmltv = reformed_xml.toprettyxml(encoding="utf-8")
    WriteLog("Finished compiling information.  Saving...")
    saveStringToFile(xmltv, "hdhomerun.xml")
    WriteLog("Finished.")


if __name__ == "__main__":
    main()
