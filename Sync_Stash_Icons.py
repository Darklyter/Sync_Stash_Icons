import random
import re
import io
import textwrap
import tempfile
import requests
from plexapi.server import PlexServer
from PIL import Image, ImageOps, ImageDraw, ImageFont
from urllib.request import urlopen
from svglib.svglib import svg2rlg
from reportlab.graphics import renderPM

plex_server = 'http://192.168.1.100:32400'          # The address of your local Plex server
plex_token = 'F-tHGyZq765YTpq23O9x'                 # The X-Plex-Token for your server (This one is only as an example, it's not valid)
                                                    # You can get information at https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/
plex_library_name = 'Websites'                      # The name of the Plex library to process

stash_instance = 'http://192.168.1.71:9999'         # Basic connection for Stash here.  Not authentication is coded in this script, either user/pass or API

file_path = '.\\output\\'                           # The subdirectory to output created images to, must be a valid directory.  Remember that for Windows you must use double slashes
create_text_posters = True                          # If there is not an image in Stash for a Tag/Site, should a text based poster be generated
attempt_to_convert_svg = False                      # If an SVG file is used in Stash, should conversion be attempted?  Be warned, results are usually not great

stash_tags_query = '{allTags{id name description image_path}}'      #Do Not Modify
stash_studios_query = '{allStudios{id name details image_path}}'    #Do not modify
plex = PlexServer(plex_server, plex_token)


def callGraphQL(query, retry=True):
    graphql_server = stash_instance + "/graphql"

    response = requests.post(graphql_server, json={"query": query})
    if response.status_code == 200:
        result = response.json()
        if result.get("data", None):
            return result
    else:
        print("GraphQL query failed to run by returning code of {}. Query: {}".format(response.status_code, query))
        raise Exception("GraphQL error")


def getImageFile(file_url):
    buffer = tempfile.SpooledTemporaryFile(max_size=1e9)
    r = requests.get(file_url, stream=True)
    if r.status_code == 200:
        downloaded = 0
        # ~ filesize = int(r.headers['content-length'])
        for chunk in r.iter_content(chunk_size=1024):
            downloaded += len(chunk)
            buffer.write(chunk)
        buffer.seek(0)
        try:
            i = Image.open(io.BytesIO(buffer.read()))
        except Exception:
            i = None
    buffer.close()
    if i:
        return i
    else:
        return None


def processImage(image, title):
    image = ImageOps.pad(image, (500, 750), color=None, centering=(0.5, 0.5))
    filename = re.sub(r'[<>:/\\|\?\*\"]+', '', title)
    filename = file_path + filename + ".png"
    image.save(filename)
    return filename


def checkForSVG(file_url):
    SVG_R = r'(?:<\?xml\b[^>]*>[^<]*)?(?:<!--.*?-->[^<]*)*(?:<svg|<!DOCTYPE svg)\b'
    SVG_RE = re.compile(SVG_R, re.DOTALL)
    f = urlopen(file_url)
    file_contents = f.read().decode('latin_1')
    is_svg = SVG_RE.match(file_contents) is not None

    return is_svg


def convertSVG(file_url):
    image = svg2rlg(file_url)
    renderPM.drawToFile(image, 'tempfile.png', fmt='PNG')
    image = Image.open('tempfile.png')
    return image


def updatePoster(title, stash_list, query_item, collection, query_type):
    update_poster = False
    for entry in stash_list['data'][query_item]:
        entry_name = re.sub(r'[^a-zA-Z0-9-+]', '', entry['name']).lower()
        if title == entry_name and "default=true" not in entry['image_path']:
            print(f"Updating {query_type} Collection: '{collection.title}' From Stash")
            image = getImageFile(entry['image_path'])
            if image:
                filename = processImage(image, collection.title)
                result = collection.uploadPoster(None, filename)
                if result:
                    update_poster = True
            else:
                if checkForSVG(entry['image_path']) and attempt_to_convert_svg:
                    print(f"Converting SVG Image for '{collection.title}', please consider replacing with PNG/JPG file")
                    image = convertSVG(entry['image_path'])
                    filename = processImage(image, collection.title)
                    result = collection.uploadPoster(entry['image_path'], None)
                    if result:
                        update_poster = True
                elif not attempt_to_convert_svg:
                    print(f"Skipping SVG conversion for: {collection.title} (Due to Config)")

    return update_poster


def rgb_to_hex(r, g, b):
    return '#{:02x}{:02x}{:02x}'.format(r, g, b)


def wrap(string, max_width):
    return '\n'.join(textwrap.wrap(string, max_width))


def createTextPoster(title):
    filename = re.sub(r'[<>:/\\|\?\*\"]+', '', title)
    filename = file_path + filename + ".png"
    width, height = (500, 750)
    color_r = random.randrange(0, 128)
    color_g = random.randrange(0, 128)
    color_b = random.randrange(0, 128)
    hex_color = rgb_to_hex(color_r, color_g, color_b)
    image = Image.new("RGB", (width, height), hex_color)
    draw = ImageDraw.Draw(image)
    font = ImageFont.truetype("Gidole-Regular.ttf", size=75)

    title = wrap(title, 15)
    font_width, font_height = draw.textbbox((0, 0), title, font=font)[2:]
    new_width = (width - font_width) / 2
    new_height = (height - font_height) / 2

    if "\n" in title:
        draw.text((new_width, new_height), title, fill="white", font=font, align="center", stroke_width=2)
    else:
        draw.text((new_width, new_height), title, fill="white", font=font, stroke_width=2)

    result = image.save(filename)
    if not result:
        print(f"Creating Default Collection Poster: {collection.title}")
        return collection.uploadPoster(None, filename)


if __name__ == "__main__":
    studio_list = callGraphQL(stash_studios_query)
    tag_list = callGraphQL(stash_tags_query)

    websites = plex.library.section(plex_library_name)

    collections = websites.collections()
    count = 0
    for collection in collections:
        count += 1
        # ~ if count < 10:
        update_result = False
        title = collection.title.lower()
        if "site:" in collection.title.lower():
            title = title.replace("site:", "").strip()
            title = re.sub(r'[^a-zA-Z0-9-+]', '', title)
            update_result = updatePoster(title, studio_list, "allStudios", collection, "Site")
        else:
            title = re.sub(r'[^a-zA-Z0-9-+]', '', title)
            update_result = updatePoster(title, tag_list, "allTags", collection, "Tag")

        if not update_result and create_text_posters:
            createTextPoster(collection.title)
        elif not update_result and not create_text_posters:
            print(f"Skipping Poster Creation for: {collection.title} (Due to Config)")
