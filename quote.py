import json
import textwrap
import string
import os
import threading
import Queue
import HTMLParser
import re

from PIL import Image as Image
from PIL import ImageDraw as ImageDraw
from PIL import ImageFont as ImageFont
import MySQLdb


class Processor(threading.Thread):
    keep_working = True
    input_queue = Queue.Queue(40)
    unescape = HTMLParser.HTMLParser()

    def __init__(self, maker):
        threading.Thread.__init__(self)
        self.maker = maker

    def run(self):
        while Processor.keep_working or not Processor.input_queue.empty():
            try:
                row = Processor.input_queue.get(timeout=1)
                self.maker.create_images(row["postid"], Processor.unescape.unescape(row["maintext"]), row["footertext"])
            except Queue.Empty:
                pass
            except ValueError:
                pass


class Writer(threading.Thread):
    keep_working = True
    input_queue = Queue.Queue(40)

    def __init__(self):
        threading.Thread.__init__(self)

    def run(self):
        while Writer.keep_working or not Writer.input_queue.empty():
            try:
                img, path = Writer.input_queue.get(timeout=1)
                img.save(path, quality=1)
            except Queue.Empty:
                pass
            except ValueError:
                pass


class Updater(threading.Thread):
    keep_working = True
    input_queue = Queue.Queue(40)

    def __init__(self, db_settings):
        threading.Thread.__init__(self)
        db = MySQLdb.connect(host=db_settings["host"],
                             user=db_settings["username"],
                             passwd=db_settings["password"],
                             db=db_settings["database"])
        self.query = db_settings["update"]
        self.cur = db.cursor(MySQLdb.cursors.DictCursor)

    def run(self):
        while Updater.keep_working or not Updater.input_queue.empty():
            try:
                qid = Updater.input_queue.get(timeout=1)
                self.cur.execute(self.query + qid)
            except Queue.Empty:
                pass
            except ValueError:
                pass


class QuoteMaker:
    def __init__(self, config, wordlist):
        QuoteMaker.error = ""
        self.check = False

        print "- Parsing '%s' file" % config
        try:
            with open(config) as data_file:
                self.settings = json.load(data_file)
        except IOError:
            print "Can not read settings file!"
            return
        except ValueError:
            print "Error in settings file syntax!"
            return

        print "- Parsing '%s' file" % wordlist
        try:
            with open(wordlist) as data_file:
                self.wordlist = set(json.load(data_file)["words"])
        except IOError:
            print "Can not read wordlist file!"
            return
        except ValueError:
            print "Error in wordlist file syntax!"
            return
        try:
            os.makedirs(self.settings["output_directory"])
        except OSError:

            pass
        print "- Loading styles"
        self.style = []
        sizes = [14, 16, 18, 20, 33, 34, 36]
        for style in self.settings["styles"]:
            style_dic = {"font_1": [],
                         "font_2": [],
                         "fontfooter": [],
                         "watermark": {},
                         "img_width": style["img_width"],
                         "img_height": style["img_height"],
                         "background-color": style.get("background-color", "#ffffff"),
                         "alignment": style["alignment"]
                         }
            font_1 = self.settings["fonts_directory"] + style["font1"]["font-family"]
            font_2 = self.settings["fonts_directory"] + style["font2"]["font-family"]
            font_foot = self.settings["fonts_directory"] + style.get("fontfooter", style["font1"])["font-family"]
            sample = None
            if "case" in style:
                if style["case"] == "upper":
                    style_dic["case"] = string.upper
                    sample = string.uppercase
                elif style["case"] == "lower":
                    style_dic["case"] = string.lower
                    sample = string.lowercase
            else:
                sample = string.letters
            for size in sizes:
                try:
                    f = ImageFont.truetype(font_1, size)
                except IOError:
                    print "Error: Can not open '%s' font!" % font_1
                    return
                h = f.getsize("A")[1]
                font = {
                    "font": f,
                    "width": sum([f.getsize(elm)[0] for elm in sample]) / (len(sample) * 1.0),
                    "height": h,
                    "margin": h + style.get("line-spacing", 1.0) * h
                }
                style_dic["font_1"].append(font)

            for size in sizes:
                try:
                    f = ImageFont.truetype(font_2, size)
                except IOError:
                    print "Error: Can not open '%s' font!" % font_2
                    return
                h = f.getsize(string.letters)[1]
                font = {
                    "font": f,
                    "width": sum([f.getsize(elm)[0] for elm in sample]) / (len(sample) * 1.0),
                    "height": h,
                    "margin": h + style.get("line-spacing", 1.0) * h
                }
                style_dic["font_2"].append(font)

            if "fontfooter" not in style:
                style_dic["fontfooter"] = style_dic["font_1"]
            else:
                for size in sizes:
                    try:
                        f = ImageFont.truetype(font_foot, size)
                    except IOError:
                        print "Error: Can not open '%s' font!" % font_foot
                        return
                    h = f.getsize(string.letters)[1]
                    font = {
                        "font": f,
                        "width": sum([f.getsize(elm)[0] for elm in sample]) / (len(sample) * 1.0),
                        "height": h,
                        "margin": h + style.get("line-spacing", 1.0) * h
                    }
                    style_dic["fontfooter"].append(font)
            style_dic["color1"] = style["font1"]["font-color"]
            style_dic["color2"] = style["font2"]["font-color"]
            style_dic["color3"] = style.get("fontfooter", style["font1"])["font-color"]

            if "left-margin" in style:
                style_dic["left-margin"] = style["left-margin"] * style["img_width"]
            else:
                style_dic["left-margin"] = 25.0

            if "right-margin" in style:
                style_dic["right-margin"] = style["right-margin"] * style["img_width"]
            else:
                style_dic["right-margin"] = 25.0

            if "top-margin" in style:
                style_dic["top-margin"] = style["top-margin"] * style["img_height"]
            if "down-margin" in style:
                style_dic["down-margin"] = style["down-margin"] * style["img_height"]

            try:
                style_dic["watermark"]["image"] = Image.open(style["watermark"]["file"])
            except IOError:
                print "Error: Can not open '%s' watermark!" % style["watermark"]["file"]
                return
            style_dic["watermark"]["image"].resize((style["watermark"]["width"], style["watermark"]["height"]))
            style_dic["watermark"]["offset_x"] = style["watermark"]["offset_x"]
            style_dic["watermark"]["offset_y"] = style["watermark"]["offset_y"]
            try:
                if style.get("background-image", "") != "":
                    style_dic["background-image"] = Image.open(style["background-image"])
                    style_dic["background-image"].resize((style["img_width"], style["img_height"]))
            except IOError:
                print "Error: Can not open '%s' background!" % style["background-image"]
                return

            style_dic["folder"] = os.path.join(self.settings["output_directory"], style["folder"]) + "/"
            try:
                os.makedirs(style_dic["folder"])
            except OSError:
                pass
            self.style.append(style_dic)
        self.pattern = re.compile(r"[\w']+|[ \-.,!?;]")
        self.url_friendly_pattern = re.compile('[\W]+')
        self.check = True

    def start(self):
        if not self.check:
            return
        print "- Generating images..."
        p_worker = Processor(self)
        p_worker.start()

        w_worker = Writer()
        w_worker.start()

        u_worker = Updater(self.settings["db"])
        u_worker.start()

        db = MySQLdb.connect(host=self.settings["db"]["host"],
                             port=self.settings["db"]["port"],
                             user=self.settings["db"]["username"],
                             passwd=self.settings["db"]["password"],
                             db=self.settings["db"]["database"])

        cur = db.cursor(MySQLdb.cursors.DictCursor)
        cur.execute(self.settings["db"]["query"])
        for row in cur.fetchall():
            p_worker.input_queue.put(row)
        print "Waiting for threads to exit..."
        Processor.keep_working = False
        p_worker.join()

        Writer.keep_working = False
        w_worker.join()

        Updater.keep_working = False
        u_worker.join()
        print "Done!"

    def create_images(self, postid, m_text, f_text):
        guess_h = 0.0
        lines = []
        font_1 = None
        font_2 = None
        font_3 = None
        margin = 0.0
        pid = str(postid)
        lookup = {
            "%postid%": pid,
            "%maintext%": self.url_friendly_pattern.sub("-", m_text[:50].lower()),
            "%footertext%": self.url_friendly_pattern.sub("-", f_text.lower())
        }
        for style in self.style:
            width = style["img_width"]
            height = style["img_height"]
            if "case" in style:
                maintext = style["case"](m_text)
                footertext = style["case"](f_text)
            else:
                maintext = m_text
                footertext = f_text
            name = style["folder"] + reduce(lambda x, y: x.replace(y, lookup[y]), lookup, self.settings["filename"])
            img = Image.new('RGB', (width, height), style["background-color"])
            if "background-image" in style:
                img.paste(style["background-image"], (0, 0))
            img.paste(style["watermark"]["image"],
                      (style["watermark"]["offset_x"],
                       style["watermark"]["offset_y"]),
                      mask=style["watermark"]["image"])
            d = ImageDraw.Draw(img)
            # Choosing font size
            for index, font in enumerate(style["font_1"]):
                self.old_h = 0.0
                lines = textwrap.wrap(maintext, width=int(
                    (width - (style["left-margin"] + style["right-margin"])) / font["width"]))
                if index < 6:
                    if index - 3 >= 0:
                        font_3 = style["fontfooter"][index - 3]
                    else:
                        font_3 = style["fontfooter"][0]
                else:
                    font_3 = style["fontfooter"][0]

                if font_3["font"].getsize(footertext)[0] <= (width - style["left-margin"] - style["right-margin"]):
                    line_width = font_3["font"].getsize(footertext)[0]
                else:
                    line_width = int((width - (style["left-margin"] + style["right-margin"])) / font_3["width"])

                guess_h = (font["margin"] * len(lines)) + font_3["margin"] * len(textwrap.wrap(footertext, line_width))
                if index == 0:
                    print "begin"
                    self.old_h = guess_h
                if "top-margin" in style and "down-margin" in style:
                    if guess_h < height - (style["top-margin"] + style["down-margin"]):
                        if self.old_h < guess_h:
                            print "guest_h: " + str(guess_h) + ", " "height: " + str(
                                height - (style["top-margin"] + style["down-margin"]))
                            font_1 = font
                            margin = font["margin"]
                            font_2 = style["font_2"][index]
                            self.old_h = guess_h
                else:
                    if guess_h < height - (style["left-margin"] + style["right-margin"]):
                        if self.old_h < guess_h:
                            font_1 = font
                            margin = font["margin"]
                            font_2 = style["font_2"][index]
                            self.old_h = guess_h
            print "\n"
            # Writing quote
            if "top-margin" not in style:
                pos = [style["left-margin"], (height - self.old_h + style["down-margin"]) / 2]
            else:
                pos = [style["left-margin"], (height - self.old_h - style["top-margin"] + style["down-margin"]) / 2]

            for line in lines:
                if style["alignment"] == "center":
                    line_width = font_1["font"].getsize(line)[0]
                    pos[0] = (width - line_width) / 2
                elif style["alignment"] == "right":
                    line_width = font_1["font"].getsize(line)[0]
                    pos[0] = width - line_width - style["right-margin"]
                else:
                    pos[0] = style["left-margin"]
                words = self.pattern.findall(line)
                tmp = ""
                for word in words:
                    if word.lower() in self.wordlist:
                        if tmp != "":
                            d.text(pos, tmp, fill=style["color1"], font=font_1["font"])
                            pos[0] += font_1["font"].getsize(tmp)[0]
                            tmp = ""
                        d.text(pos, word, fill=style["color2"], font=font_2["font"])
                        pos[0] += font_2["font"].getsize(word)[0]
                    else:
                        tmp += word
                if tmp != "":
                    d.text(pos, tmp, fill=style["color1"], font=font_1["font"])
                    pos[0] += font_1["font"].getsize(tmp)[0]
                pos[1] += margin

            # Writing Author
            if font_3["font"].getsize(footertext)[0] <= (width - style["left-margin"] - style["right-margin"]):
                line_width = font_3["font"].getsize(footertext)[0]
            else:
                line_width = int((width - (style["left-margin"] + style["right-margin"])) / font_3["width"])
            for line in textwrap.wrap(footertext, line_width):
                if style["alignment"] == "center":
                    # line_width = font_3["font"].getsize(footertext)[0]
                    pos[0] = (width - line_width) / 5
                elif style["alignment"] == "right":
                    pos[0] = (width - line_width) / 3
                else:
                    pos[0] = (width - line_width) / 8
                d.text(pos, line, fill=style["color3"], font=font_3["font"])
                pos[1] += (font_3["font"].getsize(line)[1] + font_3["font"].getsize(line)[1] / 6)
            # img.show()
            Writer.input_queue.put((img, name))
        Updater.input_queue.put(pid)


def main():
    quote_maker = QuoteMaker("settings.txt", "wordlist.txt")
    quote_maker.start()


if __name__ == "__main__":
    main()
