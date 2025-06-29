import math
import random
import json
import re
import numpy as np
import os
from scipy.interpolate import CubicSpline
from datetime import date
from io import BytesIO
import time
import zipfile
import bambulabs_api as bl


# HANDWRITING SYNTHESIS ON BAMBULAB 3D PRINTER

# OVERVIEW:
# This code wirelessly synthesizes handwriting using a BambuLab 3D printer.
# It processes a tablet-recorded character set in JSON format, converts it into G-code, and uploads the generated files via the BambuLabs API.

# USAGE:
# - Use Python 3.12 or higher, optionally in a Conda environment.
# - Make sure you have all the necessary libraries installed.
# - Enable LAN-Only mode on your BambuLab printer for connection with the API.
# - Change the print variables to suit your printer. Defaults are set for the BambuLab P1S.
# - Make sure you are within range of your printer — check the connection with OrcaSlicer or an equivalent tool.
# - Run the script to save the G-code and send it to the printer.
# - The G-code is saved in your project folder.

# WARNINGS & CONSIDERATIONS:
# - Printers other than BambuLab may have different pause and homing commands.
# - Copying formatted text with font attributes directly into the text input may cause encoding errors with BytesIO.
# - DO NOT RUN CUSTOM G-CODE ON YOUR PRINTER WITHOUT CONSTANT SUPERVISION.
# - THIS SOFTWARE CAN SEVERELY DAMAGE YOUR 3D PRINTER—USE AT YOUR OWN RISK.



# DEFINE AND SET PRINT VARIABLES ==============================


BRAND = 'BambuLab'
IP = 'IP' # only relevant for bambulab printers
SERIAL = 'SERIAL' # only relevant for bambulab printers
ACCESS_CODE = 'ACCESS CODE' # only relevant for bambulab printers
HOMING = 'G28' # the gcode command used for homing the printer
PAUSE = 'M400 U1' # the gcode command used for pausing the printer
XY_ACCELERATION = 10000  # Normal XY moves
XY_TRAVEL_ACCELERATION = 12000  # Non-extrusion travel moves
Z_ACCELERATION = 1000  # Z moves

text = """3D-Druck

3D-Druck ist eine moderne Technologie, die es ermöglicht, dreidimensionale Objekte aus verschiedenen Materialien wie Kunststoff oder Metall zu erstellen. Mithilfe von digitalen Modellen werden Schichten präzise übereinandergelegt. Diese Technik wird in vielen Bereichen eingesetzt, darunter Medizin, Industrie und Bildung, und revolutioniert die Fertigung durch individuelle und kosteneffiziente Produktion."""

font = "handwriting_block" # name of json
word_crossing_probability = 12 #percent

max_word_crossing_point_variance = 0.15 #mm
word_crossing_y_height = 0.4 #relative unit
word_crossing_x_overhang = 1 #mm
min_word_crossing_force = 0.75 #relative
max_word_crossing_force = 0.95 #relative
points_per_word_crossing_character = 15 #num of points
time_per_word_crossing_character = 0.1 #sec

pen_down_min = 67.25 #mm
pen_down_max = 66.85 #mm
pen_up = 70 #mm

pen_x_print_done = 240 #mm
pen_y_print_done = 240 #mm
pen_z_print_done = 120 #mm

pen_x_print_start = 128 #mm
pen_y_print_start = 128 #mm
pen_z_print_start = 120 #mm

x_homing = 256 #mm 256 23
y_homing = -3.1 #mm -2.5 100

print_bed_height = 256 #mm

page_x_offset = 71 #mm 63
page_y_offset = 13.75 #mm
page_width = 155 #mm

page_width_buffer = 4 #mm
page_height_buffer = 5 #mm
page_x_buffer = 6 #mm

date_x_offset = 156.5 #mm

line_height = 10 #mm

xy_travel_speed = 500 #mm/s
z_travel_speed = 20 #mm/s

speed_multiplier = 1.5 #times



# FETCH FONT DATA ========================================


font_file_path = f"{font}.json"

with open(font_file_path, "r") as json_file:
    font_data = json.load(json_file)
    print("Succesfully fetched Font File")


cursive_connection_points = font_data.get("cursive_connection_points")
cursive_connection_time = font_data.get("cursive_connection_time")

capital_character_height = font_data.get("capital_character_height")
date_capital_character_height = font_data.get("date_capital_character_height")
space_width = font_data.get("space_width")
x_spacing = font_data.get("x_spacing")

max_height_variance = font_data.get("max_height_variance")
max_x_variance = font_data.get("max_x_variance")
max_y_variance = font_data.get("max_y_variance")
min_skew = font_data.get("min_skew")
max_skew = font_data.get("max_skew")

max_stroke_point_x_variance = font_data.get("max_stroke_point_x_variance")
max_stroke_point_y_variance = font_data.get("max_stroke_point_y_variance")

new_character_variance: int = font_data.get("new_character_variance")
new_point_variance: int = font_data.get("new_point_variance")



# DEFINE FUNCTIONS =======================================



def append_gcode(x=None, y=None, z=None, f=None, travel_move=False):

    # adds a line to the gcode based on the given parameters and changes the current position

    g_code_line = []
    if travel_move: g_code_line.append("G0")
    else: g_code_line.append("G1")

    x is not None and g_code_line.append(f"X{x}")
    y is not None and g_code_line.append(f"Y{y}")
    z is not None and g_code_line.append(f"Z{z}")
    f is not None and g_code_line.append(f"F{f * speed_multiplier}")

    g_code.append(" ".join(g_code_line))
    change_current_position(new_x=x, new_y=y, new_z=z, feedrate=f * speed_multiplier, travel_move=travel_move)



def change_current_position(new_x=None, new_y=None, new_z=None, feedrate=None, travel_move=False):

    # calculates the time for a print move and adds it to the print estimate

    global current_pos
    global print_estimate

    previous_pos = current_pos.copy()
    previous_print_estimate = print_estimate
    
    new_x = new_x if new_x is not None else previous_pos[0]
    new_y = new_y if new_y is not None else previous_pos[1]
    new_z = new_z if new_z is not None else previous_pos[2]

    current_pos = [new_x, new_y, new_z]

    if new_z != previous_pos[2]: acceleration = Z_ACCELERATION
    else: acceleration = XY_TRAVEL_ACCELERATION if travel_move else XY_ACCELERATION

    distance = math.sqrt(
        (current_pos[0] - previous_pos[0]) ** 2 +
        (current_pos[1] - previous_pos[1]) ** 2 +
        (current_pos[2] - previous_pos[2]) ** 2
    )

    speed = feedrate / 60 if feedrate is not None else xy_travel_speed  

    if acceleration > 0:
        accel_time = speed / acceleration
        accel_distance = 0.5 * acceleration * (accel_time ** 2)

        if 2 * accel_distance > distance:
            accel_time = math.sqrt(distance / acceleration)
            total_time = 2 * accel_time
        else:
            cruise_distance = distance - 2 * accel_distance
            cruise_time = cruise_distance / speed
            total_time = 2 * accel_time + cruise_time
    else:
        total_time = distance / speed if speed > 0 else 0

    print_estimate += total_time

    if math.ceil(print_estimate/60) != math.ceil(previous_print_estimate/60):
        full_minute_gcode_positions.append([len(g_code)-1, math.floor(print_estimate/60)])


def append_settings():

    # adds the settings for the current print into the gcode file as comments

    g_code.append(f"; DEVICE INFO:")
    g_code.append(f"; BRAND = {BRAND}")
    g_code.append(f"; IP = {IP}")
    g_code.append(f"; SERIAL = {SERIAL}")
    g_code.append(f"; ACCESS_CODE = {ACCESS_CODE}")
    g_code.append(f"; HOMING = {HOMING}")
    g_code.append(f"; PAUSE = {PAUSE}")
    g_code.append(f"; XY_ACCELERATION = {XY_ACCELERATION}")
    g_code.append(f"; XY_TRAVEL_ACCELERATION = {XY_TRAVEL_ACCELERATION}")
    g_code.append(f"; Z_ACCELERATION = {Z_ACCELERATION}")

    g_code.append(f"")
    g_code.append(f"; INPUT:")
    g_code.append(f"; text = """ + repr(text))
    g_code.append(f"; font = {font}")

    g_code.append(f"")
    g_code.append(f"; PRINT SETTINGS:")
    g_code.append(f"; pen_down_min = {pen_down_min}")
    g_code.append(f"; pen_down_max = {pen_down_max}")
    g_code.append(f"; pen_up = {pen_up}")
    g_code.append(f"; pen_x_print_done = {pen_x_print_done}")
    g_code.append(f"; pen_y_print_done = {pen_y_print_done}")
    g_code.append(f"; pen_z_print_done = {pen_z_print_done}")
    g_code.append(f"; pen_x_print_start = {pen_x_print_start}")
    g_code.append(f"; pen_y_print_start = {pen_y_print_start}")
    g_code.append(f"; pen_z_print_start = {pen_z_print_start}")
    g_code.append(f"; x_homing = {x_homing}")
    g_code.append(f"; y_homing = {y_homing}")
    g_code.append(f"; print_bed_height = {print_bed_height}")
    g_code.append(f"; page_x_offset = {page_x_offset}")
    g_code.append(f"; page_y_offset = {page_y_offset}")
    g_code.append(f"; page_width = {page_width}")
    g_code.append(f"; page_width_buffer = {page_width_buffer}")
    g_code.append(f"; page_height_buffer = {page_height_buffer}")
    g_code.append(f"; page_x_buffer = {page_x_buffer}")
    g_code.append(f"; date_x_offset = {date_x_offset}")
    g_code.append(f"; line_height = {line_height}")
    g_code.append(f"; xy_travel_speed = {xy_travel_speed}")
    g_code.append(f"; z_travel_speed = {z_travel_speed}")

    g_code.append(f"")
    g_code.append(f"; FONT DATA:")
    g_code.append(f"; cursive_connection_points = {cursive_connection_points}")
    g_code.append(f"; cursive_connection_time = {cursive_connection_time}")
    g_code.append(f"; capital_character_height = {capital_character_height}")
    g_code.append(f"; date_capital_character_height = {date_capital_character_height}")
    g_code.append(f"; space_width = {space_width}")
    g_code.append(f"; x_spacing = {x_spacing}")
    g_code.append(f"; max_height_variance = {max_height_variance}")
    g_code.append(f"; max_x_variance = {max_x_variance}")
    g_code.append(f"; max_y_variance = {max_y_variance}")
    g_code.append(f"; min_skew = {min_skew}")
    g_code.append(f"; max_skew = {max_skew}")
    g_code.append(f"; max_stroke_point_x_variance = {max_stroke_point_x_variance}")
    g_code.append(f"; max_stroke_point_y_variance = {max_stroke_point_y_variance}")
    g_code.append(f"; new_character_variance = {new_character_variance}")
    g_code.append(f"; new_point_variance = {new_point_variance}")
    g_code.append(f"")


def append_init_gcode():

    # adds the init sequence to the gcode array

    g_code.append(f"M201 X{XY_ACCELERATION} Y{XY_ACCELERATION} Z{Z_ACCELERATION}")
    g_code.append(f"M204 T{XY_TRAVEL_ACCELERATION}")
    g_code.append(f"M204 P{XY_ACCELERATION}")

    g_code.append(f"{HOMING} X0 Y0")
    change_current_position(new_x=0, new_y=0)

    append_gcode(x=x_homing, y=y_homing, f=xy_travel_speed*60, travel_move=True)

    g_code.append(f"{HOMING} Z0")
    change_current_position(new_z=15, feedrate=z_travel_speed*60)

    append_gcode(z=pen_z_print_start, f=z_travel_speed*60, travel_move=True)
    append_gcode(x=pen_x_print_start, y=pen_y_print_start, f=xy_travel_speed*60, travel_move=True)


def remove_first(arrays):

    # removes the first item in each of the arrays and returns the result

    for i in range(len(arrays)): arrays[i] = arrays[i][1:]
    return arrays


def is_vowel(char):
    vowels = 'aeiouyäöüAEIOUYÄÖÜ'
    return char in vowels


def is_consonant(char):
    return not is_vowel(char) and char.isalpha()


def interpolate_random(lenght: int, spacing: int):

    # returns a random interpolated curve y values with a given length and spacing of new points

    extra_length = spacing - lenght % spacing
    lenght += extra_length
    x = np.arange(1, lenght + 2, spacing)
    y = np.random.uniform(-1, 1, len(x))
    x_new = np.arange(1, lenght + 1)
    cs = CubicSpline(x, y)
    y_new = cs(x_new)
    y_new_rounded = np.round(y_new, 2)
    array = y_new_rounded.tolist()

    return array


def interpolate(x, y):

    # interpolates the missing y values for a given a x array and returns the completed y array

    x_new = np.arange(1, max(x) + 1)
    cs = CubicSpline(x ,y)
    y_new = cs(x_new)
    y_new_rounded = np.round(y_new, 2)
    array = y_new_rounded.tolist()
    return array


def first_point_gcode(point):

    # adds the gcode required for the first point of a stroke to the gcode array

    append_gcode(z=pen_up, f=z_travel_speed*60, travel_move=True)
    append_gcode(x=point[0], y=point[1], f=xy_travel_speed*60, travel_move=True)
    append_gcode(z=point[2], f=z_travel_speed*60, travel_move=True)


def continious_gcode(index, point, stroke_points):

    # adds the gcode for the points in a stroke to the gcode array

    if index == 0: return

    previous_point = stroke_points[index-1]
    time_difference = point[3] - previous_point[3]
    distance = math.sqrt((point[0] - previous_point[0])**2 + (point[1] - previous_point[1])**2 + (previous_point[2] - point[2])**2)
    feedrate = round((distance / time_difference) * 60)

    append_gcode(x=point[0], y=point[1], z=point[2], f=feedrate, travel_move=False)


def create_gcode(word_strokes, cursive_array, word):

    # adds the gcode for one word based on the strokes, characters and an array that contains false or true for connections after the character

    interpolation_x = []
    interpolation_count = 1

    strokes_enum = []

    x = []
    y = []
    z = []
    times = []

    max_time = 0

    for index, character_strokes in enumerate(word_strokes):
        for stroke_points in character_strokes:
            for point in stroke_points:
                interpolation_x.append(interpolation_count)
                x.append(point[0])
                y.append(point[1])
                z.append(point[2])
                times.append(round((point[3] + max_time)*1000)/1000)
                interpolation_count += 1

            if not stroke_points == character_strokes[-1]:
                max_time = max(times) + 0.05
                strokes_enum.append(interpolation_count)
            else: max_time = max(times)
        

        if not character_strokes == word_strokes[-1] and cursive_array[0] == True and word[index+1].isalpha():
            interpolation_count += cursive_connection_points

            for i in range(cursive_connection_points):
                times.append(round((max_time + (cursive_connection_time / cursive_connection_points))*1000)/1000)
                max_time = max(times)
            
            max_time += 0.05

        elif not character_strokes == word_strokes[-1]:
            max_time = max(times) + 0.05
            strokes_enum.append(interpolation_count)

        cursive_array = cursive_array[1:]


    interpolated_x = interpolate(interpolation_x, x)
    interpolated_y = interpolate(interpolation_x, y)
    interpolated_z = interpolate(interpolation_x, z)

    points = [list(point) for point in zip(interpolated_x, interpolated_y, interpolated_z, times)]

    first_point_gcode(points[0])

    for index, point in enumerate(points):
        
        if index + 1 in strokes_enum and not index == 0: first_point_gcode(point)
        else: continious_gcode(index, point, points)


def process_character_points(character, character_x_offset, character_y_offset, character_height_offset, character_skew):

    # returns a stroke array based on the character and adds variances to each character and stroke point, the max stroke point x value and an array containing the cursive information

    max_x_value = 0
    character_strokes = []

    character_versions = font_data.get(character, [])
    if character_versions == []:
        print(f"empty array for character: {character}")
    
    character_cursive = character_versions[0]
    character_versions = character_versions[1:]

    strokes = random.choice(character_versions)

    number_of_stroke_points = 0
    for stroke in strokes:
        number_of_stroke_points += len(stroke)

    stroke_point_x_variances = interpolate_random(number_of_stroke_points, new_point_variance)
    stroke_point_y_variances = interpolate_random(number_of_stroke_points, new_point_variance)

    for stroke_points in strokes:
        
        stroke = []

        for point in stroke_points:

            stroke_point_x_offset = (max_stroke_point_x_variance * stroke_point_x_variances[0])
            stroke_point_y_offset = (max_stroke_point_y_variance * stroke_point_y_variances[0])
            stroke_point_x_variances, stroke_point_y_variances = remove_first([stroke_point_x_variances, stroke_point_y_variances])

            skew_x_offset = (-point[1] + stroke_point_y_offset) * character_skew

            point_x = round((point[0] * (capital_character_height + character_height_offset) + character_x_offset + stroke_point_x_offset + skew_x_offset)*100)/100
            point_y = round((-point[1] * (capital_character_height + character_height_offset) + character_y_offset + stroke_point_y_offset)*100)/100

            relative_x_value = round((point[0] * (capital_character_height + character_height_offset) + stroke_point_x_offset)*100)/100

            if relative_x_value > max_x_value:
                max_x_value = relative_x_value

            point_force = point[2]
            point_time = point[3]
            point_z = round((pen_down_min + (point_force * (pen_down_max - pen_down_min)))*100)/100

            stroke_point = [point_x, point_y, point_z, point_time]
            stroke.append(stroke_point)
    
        character_strokes.append(stroke)
    
    return character_strokes, max_x_value, character_cursive




# INIT ===================================================


g_code = []
lines = text.splitlines()

print_estimate = 0
current_pos = [128, 128, 128]

full_minute_gcode_positions = []

title = "_".join(lines[0].split())
g_code_file_path = f"{title}"

append_settings()
append_init_gcode()



# CREATE DATE GCODE =======================================


today = date.today()
date_string = today.strftime("%d.%b.%y")

date_lenght = len(date_string)

date_x_variances = interpolate_random(date_lenght, new_character_variance)
date_y_variances = interpolate_random(date_lenght, new_character_variance)
date_height_variances = interpolate_random(date_lenght, new_character_variance)
date_skew_variances= interpolate_random(date_lenght, new_character_variance)

date_strokes = []
date_cursive_array = []
date_character_x_offset = page_x_offset + date_x_offset

for character in date_string:

    date_character_x_offset += (max_x_variance * date_x_variances[0])
    date_character_y_offset = print_bed_height - page_y_offset + (max_y_variance * date_y_variances[0])
    date_character_height_offset = max_height_variance * date_height_variances[0]
    date_character_skew = min_skew + (date_skew_variances[0] + 1) * (max_skew - min_skew) / 2

    date_x_variances, date_y_variances, date_height_variances, date_skew_variances = remove_first([date_x_variances, date_y_variances, date_height_variances, date_skew_variances])
    character_strokes, max_x_value, character_cursive = process_character_points(character, date_character_x_offset, date_character_y_offset, date_character_height_offset, date_character_skew)
    
    if character in ["T", "F", "P", "Y", "V"]:
        date_character_x_offset += max_x_value
    else:
        date_character_x_offset += x_spacing + max_x_value
    
    date_strokes.append(character_strokes)
    date_cursive_array.append(character_cursive)

create_gcode(date_strokes, date_cursive_array, date_string)



# CREATE TEXT GCODE =======================================


word_x_offset = page_x_offset + page_x_buffer
word_y_offset = print_bed_height - page_y_offset

for line in lines:

    if line == "":

        word_x_offset = page_x_buffer + page_x_offset
        word_y_offset -= line_height

        continue

    raw_words = re.findall(r'\S+|\s+', line)
    words = []
    crossed_out_words = []

    for word in raw_words:

        if random.randint(1, 100) <= word_crossing_probability * 3 and len(word) >= 5 and word.replace(" ", "") != "":
            mistake_pos = random.randint(3, len(word)-2)
            last_character = word[-1]
        
            if word[mistake_pos] != last_character and ((is_vowel(word[mistake_pos]) and is_vowel(last_character))or(is_consonant(word[mistake_pos]) and is_consonant(last_character))):
                misspelled_word = word[:mistake_pos] + word[-1]
                print(f"misspelled_word: {misspelled_word}; original word: {word}")
                words.append(misspelled_word)
                crossed_out_words.append(misspelled_word)
                words.append(" ")

        words.append(word)

    number_of_characters = len("".join(words))

    x_variances = interpolate_random(number_of_characters, new_character_variance)
    y_variances = interpolate_random(number_of_characters, new_character_variance)
    height_variances = interpolate_random(number_of_characters, new_character_variance)
    skew_variances = interpolate_random(number_of_characters, new_character_variance)

    for word in words:

        if word.replace(" ", "") == "":

            for character in word:
                if word_x_offset <= character_x_offset:
                    word_x_offset = character_x_offset + space_width + 3 * (max_x_variance * x_variances[0])
                else:
                    word_x_offset = word_x_offset + space_width + 3 * (max_x_variance * x_variances[0])
                x_variances, y_variances, height_variances, skew_variances = remove_first([x_variances, y_variances, height_variances, skew_variances])
    
            continue

        word_strokes = []
        cursive_array = []
        character_x_offset = word_x_offset

        for character in word:

            character_x_offset += (max_x_variance * x_variances[0])
            character_y_offset = word_y_offset + (max_y_variance * y_variances[0])
            character_height_offset = max_height_variance * height_variances[0]
            character_skew = min_skew + (skew_variances[0] + 1) * (max_skew - min_skew) / 2
            x_variances, y_variances, height_variances, skew_variances = remove_first([x_variances, y_variances, height_variances, skew_variances])

            character_strokes, max_x_value, character_cursive = process_character_points(character, character_x_offset, character_y_offset, character_height_offset, character_skew)
            
            word_strokes.append(character_strokes)
            cursive_array.append(character_cursive)

            if character in ["T", "F", "P", "Y", "V"]:
                character_x_offset += max_x_value
            else:
                character_x_offset += x_spacing + max_x_value

        x_values = [point[0] for subarray2 in word_strokes for subarray1 in subarray2 for point in subarray1]

        if max(x_values) >= page_x_offset + page_width - page_width_buffer:
            for character_strokes in word_strokes:
                for stroke in character_strokes:
                    for stroke_point in stroke:
                        stroke_point[0] -= (word_x_offset - page_x_buffer - page_x_offset)
                        stroke_point[1] -= line_height
            
            character_x_offset -= (word_x_offset - page_x_buffer - page_x_offset)

            word_x_offset = page_x_buffer + page_x_offset
            word_y_offset -= line_height

        y_values = [point[1] for subarray2 in word_strokes for subarray1 in subarray2 for point in subarray1]

        if min(y_values) <= 0 + page_height_buffer:
            for character_strokes in word_strokes:
                for stroke in character_strokes:
                    for stroke_point in stroke:
                        stroke_point[1] += print_bed_height - (word_y_offset + page_y_offset)
            
            character_y_offset += print_bed_height - (word_y_offset + page_y_offset)
            word_y_offset = print_bed_height - page_y_offset

            append_gcode(z=pen_z_print_start, f=z_travel_speed*60, travel_move=True)
            g_code.append(PAUSE)
            append_gcode(x=pen_x_print_start, y=pen_y_print_start, f=xy_travel_speed*60)
            append_init_gcode()

        create_gcode(word_strokes, cursive_array, word)

        if word in crossed_out_words:

            x_values = [point[0] for subarray2 in word_strokes for subarray1 in subarray2 for point in subarray1]
            
            raw_cross_out_stroke_y = interpolate_random(len(word) * points_per_word_crossing_character, new_point_variance)
            cross_out_stroke_x = list(np.linspace(min(x_values) - word_crossing_x_overhang, max(x_values) + word_crossing_x_overhang, len(word) * points_per_word_crossing_character))
            cross_out_stroke_force = interpolate_random(len(word) * points_per_word_crossing_character, new_point_variance)
            cross_out_stroke_time = list(np.linspace(0, len(word) *  time_per_word_crossing_character, len(word) * points_per_word_crossing_character))
            
            cross_out_stroke_y = []
            cross_out_stroke_z = []

            for cross_out_point_y in raw_cross_out_stroke_y:
                cross_out_stroke_y.append(word_y_offset + (word_crossing_y_height * capital_character_height) + (cross_out_point_y * max_word_crossing_point_variance))

            for cross_out_point_force in cross_out_stroke_force:
                cross_out_stroke_z.append(pen_down_min + ((((cross_out_point_force + 1) / 2) * (max_word_crossing_force - min_word_crossing_force) + min_word_crossing_force) * (pen_down_max - pen_down_min)))

            cross_out_stroke = []

            for index, point in enumerate(cross_out_stroke_time):

                stroke_point_value_array = [cross_out_stroke_x[index], cross_out_stroke_y[index], cross_out_stroke_z[index], cross_out_stroke_time[index]]
                cross_out_stroke.append(stroke_point_value_array)

            for index, point in enumerate(cross_out_stroke):

                if index == 0: first_point_gcode(point)
                else: continious_gcode(index, point, cross_out_stroke)
            

    word_x_offset = page_x_offset + page_x_buffer
    word_y_offset -= line_height



# APPEND END GCODE SEQUENCE AND SAVE GCODE FILE ========


append_gcode(z=pen_z_print_done, f=z_travel_speed*60, travel_move=True)
append_gcode(x=pen_x_print_done, y=pen_y_print_done, f=xy_travel_speed*60, travel_move=True)

print_minutes = math.floor(print_estimate/60)
print_seconds = round(print_estimate - (print_minutes*60))

for full_minute_position in reversed(full_minute_gcode_positions):
    remaining_minutes = print_minutes - full_minute_position[1]
    percent = round(((print_minutes - remaining_minutes) / print_minutes) * 1000) / 10
    g_code.insert(full_minute_position[0], f"M73 P{percent} R{remaining_minutes}")

g_code_content = formatted_string = "\n".join(g_code)
g_code_content += "\n"

if os.path.exists(f"{g_code_file_path}.gcode"):

    count = 1

    while os.path.exists(f"{g_code_file_path}_{count}.gcode"): count += 1
    g_code_file_path = f"{g_code_file_path}_{count}"

with open(f"{g_code_file_path}.gcode", "x") as gcode_file:
    gcode_file.write(g_code_content)
    print(f"Saved G-Code as {g_code_file_path}.gcode")

print(f"The Print will take {print_minutes}m_{print_seconds}s")



# UPLOAD GCODE TO BAMBULAB PRINTER ======================


if BRAND.replace(" ", "").lower() == "bambulab":

    env = os.getenv("env", "debug")

    def create_zip_archive_in_memory(text_content: str, text_file_name: str = 'file.txt') -> BytesIO:

        zip_buffer = BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zipf:
            zipf.writestr(text_file_name, text_content)
        zip_buffer.seek(0)
        return zip_buffer


    if __name__ == '__main__':

        print('Connecting to Bambulab 3D printer')
        print(f'IP: {IP}')
        print(f'Serial: {SERIAL}')
        print(f'Access Code: {ACCESS_CODE}')

        printer = bl.Printer(IP, ACCESS_CODE, SERIAL)

        printer.connect()

        time.sleep(5)

        with open(f"{g_code_file_path}.gcode", "r") as file:
            gcode = file.read()

        gcode_location = "Metadata/plate_1.gcode"
        io_file = create_zip_archive_in_memory(gcode, gcode_location)

        if not printer.get_state == 'IDLE':

            printer.stop_print()
            time.sleep(5)

        if file:
            result = printer.upload_file(io_file, f"{g_code_file_path}_{print_minutes}m_{print_seconds}s.3mf")
            if "226" not in result:
                print("Error Uploading File to Printer; Please Check if your Text Contains Attributes")

            else:
                print("Done Uploading File to Printer")
                printer.start_print(f"{g_code_file_path}_{print_minutes}m_{print_seconds}s.3mf", 1)
                print("Print Command Sent")
