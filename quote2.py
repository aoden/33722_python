import json
from multiprocessing.pool import ThreadPool, Pool
import re
import string
import errno
import os

from PIL import Image as Image
from PIL import ImageDraw as ImageDraw
from PIL import ImageFont as ImageFont
import MySQLdb


class QuoteMaker:
    def __init__(self):

        with open("settings.txt") as data_file:
            self.settings = json.load(data_file)
        self.db = MySQLdb.connect(host=self.settings["db"]["host"],
                                  user=self.settings["db"]["username"],
                                  passwd=self.settings["db"]["password"],
                                  db=self.settings["db"]["database"])
        self.cur = self.db.cursor(MySQLdb.cursors.DictCursor)
        self.query = self.settings["db"]["query"]
        self.update = self.settings["db"]["update"]
        self.styles = self.settings["styles"]
        self.pattern = re.compile(r"[\w']+|[ \-.,!?;]")
        self.url_friendly_pattern = re.compile('[\W]+')

    def write(self):
        params = []
        self.cur.execute(self.query)
        data = self.cur.fetchall()
        for style in self.styles:
            make_sure_path_exists(self.settings["output_directory"] + "/" + style["folder"])
            for row in data:
                self.cur.execute(self.update + str(row["postid"]))
                tuple = (row, style, self.settings, self.url_friendly_pattern)
                params.append(tuple)
        p = Pool(20)
        p.map(do_process, params)


def make_sure_path_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


def do_process(param):
    row, style, settings, pattern = param[0], param[1], param[2], param[3]
    sample = None
    if "case" in style:
        if style["case"] == "upper":
            maintext = str.upper(row["maintext"])
            footertext = str.upper(row["footertext"])
            sample = string.uppercase
        else:
            maintext = str.lower(row["maintext"])
            footertext = str.lower(row["footertext"])
            sample = string.lowercase
    else:
        maintext = row["maintext"]
        footertext = row["footertext"]
        sample = string.uppercase
    width = style["img_width"]
    height = style["img_height"]
    lookup = {
        "%postid%": str(row["postid"]),
        "%maintext%": pattern.sub("-", maintext[:50].lower()),
        "%footertext%": pattern.sub("-", footertext.lower())
    }
    name = style["folder"] + "/" + reduce(lambda x, y: x.replace(y, lookup[y]), lookup,
                                          settings["filename"])
    img = Image.new('RGB', (width, height), style["background-color"])
    water_mark = Image.open(style["watermark"]["file"])
    water_mark.resize((style["watermark"]["width"], style["watermark"]["height"]))
    if "background-image" in style:
        img.paste(Image.open(style["background-image"]), (0, 0))
    img.paste(water_mark,
              (style["watermark"]["offset_x"],
               style["watermark"]["offset_y"]),
              mask=water_mark)
    draw = ImageDraw.Draw(img)
    max_font_size = style["max_font_size"]
    min_font_size = style["min_font_size"]
    font_1 = settings["fonts_directory"] + style["font1"]["font-family"]
    font_2 = settings["fonts_directory"] + style["font2"]["font-family"]
    font_foot = settings["fonts_directory"] + style.get("fontfooter", style["font1"])["font-family"]

    left_margin = style["left-margin"]
    right_margin = style["right-margin"]
    top_margin = style["top-margin"]
    down_margin = style["down-margin"]
    # calculate margins
    if "left-margin" in style:
        left_margin = style["left-margin"] * style["img_width"]
    else:
        style["left-margin"] = 25.0
    if "right-margin" in style:
        right_margin = style["right-margin"] * style["img_width"]
    else:
        style["right-margin"] = 25.0
    if "top-margin" in style:
        top_margin = style["top-margin"] * style["img_height"]
    if "down-margin" in style:
        down_margin = style["down-margin"] * style["img_height"]

    # calculate font size
    size = max_font_size

    max_box_h = height - top_margin - down_margin
    box_h = 2 * max_box_h
    while box_h > max_box_h and size > min_font_size:
        f = ImageFont.truetype(font_1, size)
        foot_f = ImageFont.truetype(font_foot, int(size * style["footer_size"]))

        h = f.getsize("A")[1]
        font = {
            "font": f,
            "width": sum([f.getsize(elm)[0] for elm in sample]) / (len(sample) * 1.0),
            "height": h,
            "margin": h + style["line-spacing"] * h
        }
        h = foot_f.getsize("A")[1]
        font_f = {
            "font": foot_f,
            "width": sum([foot_f.getsize(elm)[0] for elm in sample]) / (len(sample) * 1.0),
            "height": h,
            "margin": h + style["line-spacing"] * h
        }
        box_w = int(style["img_width"] - left_margin - right_margin)
        lines = wrap_text(maintext, box_w, f)
        foot_lines = wrap_text(footertext, box_w, foot_f)
        # calculate height of main and footer text
        footer_h = 0.0
        main_h = 0.0
        for line in foot_lines:
            footer_h += font_f["margin"]
        for line in lines:
            main_h += font["margin"]
        box_h = main_h + footer_h + font_f["margin"] / 2
        size -= 1

    # print(len(lines))
    pad = font["margin"]
    current_h = int(style["img_height"] + top_margin - down_margin - box_h) / 2
    for line in lines:
        w, h = f.getsize(line)
        if style["alignment"] == "center":
            draw.text(((width - w) / 2, current_h), line, font=f, fill=style["font1"]["font-color"])
        elif style["alignment"] == "left":
            draw.text((left_margin, current_h), line, font=f, fill=style["font1"]["font-color"])
        else:
            draw.text((width - w - right_margin, current_h), line, font=f, fill=style["font1"]["font-color"])
        current_h += pad
        # img.save(settings["output_directory"] + "/" + name)

    pad = font_f["margin"]
    current_h += pad / 2
    for line in foot_lines:
        w, h = foot_f.getsize(line)
        if style["alignment"] == "center":
            draw.text(((width - w) / 2, current_h), line, font=foot_f,
                      fill=style["fontfooter"]["font-color"])
        elif style["alignment"] == "left":
            draw.text((left_margin, current_h), line, font=foot_f, fill=style["fontfooter"]["font-color"])
        else:
            draw.text((width - w - right_margin, current_h), line, font=foot_f,
                      fill=style["fontfooter"]["font-color"])
        current_h += pad
    img.save(settings["output_directory"] + "/" + name)


def count_letters(word):
    return len(word) - word.count(' ')


def wrap_text(text, width, font):
    text_lines = []
    text_line = []
    text = text.replace('\n', ' [br] ')
    words = text.split()
    font_size = font.getsize(text)

    for word in words:
        if word == '[br]':
            text_lines.append(' '.join(text_line))
            text_line = []
            continue
        text_line.append(word)
        w, h = font.getsize(' '.join(text_line))
        if w > width:
            text_line.pop()
            text_lines.append(' '.join(text_line))
            text_line = [word]

    if len(text_line) > 0:
        text_lines.append(' '.join(text_line))

    return text_lines


def main():
    p = QuoteMaker()
    print("Writing images...")
    p.write()
    print("Done!")


if __name__ == "__main__":
    main()
