from __future__ import absolute_import

import cocos
from cocos.director import director

import pyglet
import pygame
import tkinter as tk
from tkinter import filedialog

from imgui.integrations.cocos2d import ImguiLayer
import imgui
import numpy as np
import math
import itertools
from enum import Enum

import time
import os
import sys
import cv2

path = os.path.abspath('FBA_MATTING')
if path not in sys.path:
    sys.path.append(path)
from FBA_Matting.demo import pred
from FBA_Matting.networks.models import build_model
import matplotlib.pyplot as plt
from PIL import Image
import PIL
from utils import update_texture


# TODO:
# 1. Using imgui.ini
# 2. Add preview window. (Predict Alpha, masked_image with predict alpha, predict background, predict foreground)
# 3. Zoom in / out
# 4. Brush radius visualization
# 5. Speed up.
#  - Trimap make gray.
#  - Make trimap update faster.
#  - Using shader to display blended result.
#  - Remove duplicated process. Especially in predict process.
#  - Accelerate image processing process. ( i.e. Upscale from prediction result )
# 6. 점을 찍을 수 있어야 된다. 현재 드래그만 됨.
# 7. Undo / Redo


class Matting_Model_Args:
    encoder = 'resnet50_GN_WS'
    decoder = 'fba_decoder'
    weights = 'FBA_Matting/pretrained/FBA.pth'  # Relative path from current script


class Color(Enum):
    FOREGROUND = [255, 255, 255]
    BACKGROUND = [0, 0, 0]
    UNKNOWN = [127, 127, 127]


class HelloWorld(ImguiLayer):
    is_event_handler = True

    def __init__(self):
        super(HelloWorld, self).__init__()
        self._model_dim = 512

        # Texture ids.
        self._predict_alpha_texture_id = (pyglet.gl.GLuint * 1)()
        self._trimap_image_texture_id = (pyglet.gl.GLuint * 1)()
        self._image_texture_id = (pyglet.gl.GLuint * 1)()

        self._text = "Input text here"
        self._drag_start_pos = []
        self._drag_started = False
        self._prev_mouse_pos = []
        self._brush_radius = 3  # pixel
        self._brush_color = Color.FOREGROUND
        self._image_window_size = [400, 400]  # Load from imgui.ini

        # Images
        self._image = None
        self._trimap = None
        self._resized_trimap = None
        self._blended_image = None
        self._float_image = None
        self._image_path = None
        self._predict_alpha = None
        self._predict_foreground = None
        self._predict_background = None
        self._height = -1
        self._width = -1

        self._matting_model = build_model(Matting_Model_Args())
        self._trimap_update_history = []  # Store points information for undo, redo.
        self._trimap_transparency = 0.5

        # Control window variable
        self._selected_brush_index = 0  # 0 : Fore, 1 : Back, 2 : Unknown, 3 : Undefined(Not used)

        # Disable buffer alignment. Default 4.
        pyglet.gl.glPixelStorei(pyglet.gl.GL_PACK_ALIGNMENT, 1)
        pyglet.gl.glPixelStorei(pyglet.gl.GL_UNPACK_ALIGNMENT, 1)

        # Generate displacement table
        self._displacement_table = []
        self.update_brush_size(5)

    def load_image(self, path_to_image):
        try:
            image = np.array(Image.open(path_to_image))
            if image is not None:
                # If there are image, clean up variables.
                self._image = image
                self._image_path = path_to_image
                self._trimap = None
                self._resized_trimap = None
                self._blended_image = None
                self._float_image = None
                self._image_path = None
                self._predict_alpha = None
                self._predict_foreground = None
                self._predict_background = None
                self._height = -1
                self._width = -1

                # Clear gl

                self._image = self._image.astype(np.uint8)
                self._float_image = cv2.resize(self._image, (self._model_dim, self._model_dim)) / 255.0
                self._height = self._image.shape[0]
                self._width = self._image.shape[1]
                self._trimap = np.zeros((self._height, self._width, 3)).astype(np.uint8)
                self._trimap[:, :] = Color.BACKGROUND.value
                self._resized_trimap = np.zeros((self._model_dim, self._model_dim), dtype=np.uint8)
                self._predict_alpha = np.zeros((self._height, self._width, 3)).astype(np.uint8)
                self.update_blended_image()

                # Create image texture
                pyglet.gl.glGenTextures(1, self._image_texture_id)
                update_texture(self._image_texture_id[0], pyglet.gl.GL_RGB,
                               self._width, self._height, self._blended_image.tobytes())

                # Create trimap texture
                pyglet.gl.glGenTextures(1, self._trimap_image_texture_id)
                update_texture(self._trimap_image_texture_id[0], pyglet.gl.GL_RGB,
                               self._width, self._height, self._trimap.tobytes())

                # Create predict alpha texture
                pyglet.gl.glGenTextures(1, self._predict_alpha_texture_id)
                update_texture(self._predict_alpha_texture_id[0], pyglet.gl.GL_RGB,
                               self._width, self._height, self._predict_alpha.tobytes())
                self.predict()
                self._image_path = path_to_image
                self._image = np.array(Image.open(self._image_path))
        except PIL.UnidentifiedImageError:
            print('Selected file is not a image file')

    def save_image(self, path_to_save):
        if self._predict_alpha is not None:
            cv2.imwrite(path_to_save, cv2.cvtColor(self._predict_alpha, cv2.COLOR_RGB2GRAY))

    def update_brush_size(self, brush_radius):
        self._brush_radius = brush_radius
        self._displacement_table = []
        for displacement_x in range(-self._brush_radius, self._brush_radius + 1):
            for displacement_y in range(-self._brush_radius, self._brush_radius + 1):
                if math.sqrt(displacement_x * displacement_x + displacement_y * displacement_y) <= self._brush_radius:
                    self._displacement_table.append((displacement_x, displacement_y))

    def clear_trimap(self, trimap_color=None):
        if trimap_color == None:
            self._trimap[:, :] = Color.UNDEFINED.value
        else:
            self._trimap[:, :] = trimap_color.value

        self.update_blended_image()
        update_texture(self._image_texture_id[0], pyglet.gl.GL_RGB,
                       self._width, self._height, self._blended_image.tobytes())
        update_texture(self._trimap_image_texture_id[0], pyglet.gl.GL_RGB,
                       self._width, self._height, self._trimap.tobytes())
        self.predict()

    def predict(self):
        self._resized_trimap = cv2.resize(cv2.cvtColor(self._trimap, cv2.COLOR_RGB2GRAY), (self._model_dim, self._model_dim)) / 255.0
        h, w = self._resized_trimap.shape
        model_trimap = np.zeros((h, w, 2))
        model_trimap[self._resized_trimap == 1, 1] = 1
        model_trimap[self._resized_trimap == 0, 0] = 1

        st = time.perf_counter()
        _, _, alpha = pred(self._float_image, model_trimap, self._matting_model)
        elapsed_time = time.perf_counter() - st
        print('Prediction time : {}'.format(elapsed_time))
        self._predict_alpha = cv2.resize(cv2.cvtColor(alpha * 255.0, cv2.COLOR_GRAY2RGB), (self._width, self._height)).astype(np.uint8)
        update_texture(self._predict_alpha_texture_id[0], pyglet.gl.GL_RGB,
                       self._width, self._height, self._predict_alpha.tobytes())
        elapsed_time = time.perf_counter() - st
        print('Image processing time : {}'.format(elapsed_time))

    def update_blended_image(self, point_indices=None):
        if point_indices == None:
            self._blended_image = self._image * (1.0 - self._trimap_transparency) + self._trimap * self._trimap_transparency
            self._blended_image = self._blended_image.astype(np.uint8)
        else:
            self._blended_image[point_indices] = self._image[point_indices] * (1.0 - self._trimap_transparency) + \
                                                 self._trimap[point_indices] * self._trimap_transparency
            self._blended_image = self._blended_image.astype(np.uint8)

    # TODO : Apply interpolation algorithm.
    def update_trimap(self, current_mouse_pos):
        # List up calculation point
        displacement_x = current_mouse_pos[0] - self._prev_mouse_pos[0]
        displacement_y = current_mouse_pos[1] - self._prev_mouse_pos[1]

        if displacement_x == 0 and displacement_y == 0:
            return

        if displacement_x == 0:
            y_list = np.arange(self._prev_mouse_pos[1], current_mouse_pos[1],
                               1 if current_mouse_pos[1] >= self._prev_mouse_pos[1] else -1)
            y_list = np.append(y_list, current_mouse_pos[1])
            points = list(zip(itertools.repeat(current_mouse_pos[0]), y_list))

        elif displacement_y == 0:
            x_list = np.arange(self._prev_mouse_pos[0], current_mouse_pos[0],
                               1 if current_mouse_pos[0] >= self._prev_mouse_pos[0] else -1)
            x_list = np.append(x_list, current_mouse_pos[0])
            points = list(zip(x_list, itertools.repeat(current_mouse_pos[1])))
        else:
            a = (current_mouse_pos[1] - self._prev_mouse_pos[1]) / (current_mouse_pos[0] - self._prev_mouse_pos[0])
            b = (current_mouse_pos[1] - a * current_mouse_pos[0])

            if abs(displacement_x) >= abs(displacement_y):
                x_list = np.arange(self._prev_mouse_pos[0], current_mouse_pos[0],
                                   1 if current_mouse_pos[0] >= self._prev_mouse_pos[0] else -1)
                x_list = np.append(x_list, current_mouse_pos[0])
                y_list = a * x_list + b
                points = list(zip(x_list, y_list))
            else:
                y_list = np.arange(self._prev_mouse_pos[1], current_mouse_pos[1],
                                   1 if current_mouse_pos[1] >= self._prev_mouse_pos[1] else -1)
                y_list = np.append(y_list, current_mouse_pos[1])
                x_list = (y_list - b) / a
                points = list(zip(x_list, y_list))

        update_coord = set()
        for point in points:
            x = point[0]
            y = point[1]
            for displacement in self._displacement_table:
                disp_x = displacement[0]
                disp_y = displacement[1]

                # Check boundaries
                if x + disp_x < 0 or x + disp_x >= self._width:
                    continue

                if y + disp_y < 0 or y + disp_y >= self._height:
                    continue

                update_coord.add((int(y + disp_y), int(x + disp_x)))

        update_indices = tuple(zip(*update_coord))
        self._trimap[update_indices] = self._brush_color.value
        self.update_blended_image(update_indices)
        update_texture(self._image_texture_id[0], pyglet.gl.GL_RGB,
                       self._width, self._height, self._blended_image.tobytes())
        update_texture(self._trimap_image_texture_id[0], pyglet.gl.GL_RGB,
                       self._width, self._height, self._trimap.tobytes())

    def draw(self, *args, **kwargs):
        imgui.new_frame()

        # Keyboard input handling. Some of keyboard input won't work.
        # io = imgui.get_io()
        # for i in range(len(io.keys_down)):
        #     if io.keys_down[i]:
        #         print(i)

        ################
        # Top menu bar #
        ################

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):
                clicked_open, _ = imgui.menu_item('Open')
                if clicked_open:
                    root = tk.Tk()
                    root.withdraw()
                    image_path = filedialog.askopenfilename()
                    if len(image_path) != 0:
                        self.load_image(image_path)

                clicked_save, _ = imgui.menu_item('save')
                if clicked_save:
                    root = tk.Tk()
                    root.withdraw()
                    image_path = filedialog.asksaveasfilename()
                    self.save_image(image_path)

                imgui.separator()
                clicked_quit, selected_quit = imgui.menu_item(
                    "Quit", 'Cmd+Q', False, True
                )

                if clicked_quit:
                    exit(1)

                imgui.end_menu()
            imgui.end_main_menu_bar()

        ################
        # Image window #
        ################
        # ConfigWindowsMoveFromTitleBarOnly not mapped yet in PyImGui.
        if self._image is not None:
            imgui.set_next_window_size(self._image_window_size[0], self._image_window_size[1])
            imgui.begin("Image", flags=imgui.WINDOW_HORIZONTAL_SCROLLING_BAR + imgui.WINDOW_NO_MOVE)

            # Get position info to calculate mouse pos on image.
            window_pos = imgui.get_window_position()
            mouse_pos = imgui.get_mouse_position()
            cursor_pos = imgui.get_cursor_pos()
            scroll_y_pos = imgui.get_scroll_y()
            scroll_x_pos = imgui.get_scroll_x()
            relative_pos = [mouse_pos[0] - window_pos[0] - cursor_pos[0] + scroll_x_pos,
                            mouse_pos[1] - window_pos[1] - cursor_pos[1] + scroll_y_pos]

            # Mouse right click menu activity : selectable not work very well.
            if imgui.is_window_hovered() and imgui.is_mouse_clicked(2):
                imgui.open_popup('Image menu')

            if imgui.begin_popup('Image menu'):
                imgui.text('Menu')
                imgui.separator()
                if imgui.begin_menu('Clear image'):
                    _, selected = imgui.menu_item('Foreground')
                    if selected:
                        self.clear_trimap(Color.FOREGROUND)
                    _, selected = imgui.menu_item('Background')
                    if selected:
                        self.clear_trimap(Color.BACKGROUND)
                    _, selected = imgui.menu_item('Unknown')
                    if selected:
                        self.clear_trimap(Color.UNKNOWN)

                    imgui.end_menu()
                imgui.end_popup()

            # Mouse activity
            if imgui.is_mouse_clicked(0) and imgui.is_window_hovered():
                self._drag_start_pos = relative_pos
                self._prev_mouse_pos = relative_pos

            if imgui.is_mouse_dragging(0) and imgui.is_window_hovered():
                if not self._drag_started:
                    self._drag_started = True
                self.update_trimap(relative_pos)
                self._prev_mouse_pos = relative_pos
            else:
                if self._drag_started:
                    self._drag_started = False
                    self.predict()

            imgui.image(self._image_texture_id[0], self._width, self._height)
            imgui.get_window_draw_list().add_circle(mouse_pos[0], mouse_pos[1], self._brush_radius,
                                                    imgui.get_color_u32_rgba(1, 0, 0, 1), thickness=2.0)
            current_window_size = imgui.get_window_size()
            self._image_window_size = [current_window_size[0], current_window_size[1]]
            imgui.end()

        if self._predict_alpha is not None:
            imgui.begin("Alpha", flags=imgui.WINDOW_HORIZONTAL_SCROLLING_BAR)
            imgui.image(self._predict_alpha_texture_id[0], self._width, self._height)
            imgui.end()

        ######################################################################

        imgui.begin('Image menu')
        clicked, current = imgui.combo('Brush type', self._selected_brush_index,
                                       ['Foreground', 'Background', 'Unknown'])
        if clicked:
            self._selected_brush_index = current

            if current == 0:
                self._brush_color = Color.FOREGROUND
            elif current == 1:
                self._brush_color = Color.BACKGROUND
            else:
                self._brush_color = Color.UNKNOWN

        changed, value = imgui.slider_int('Brush radius', self._brush_radius, 1, 15)
        if changed:
            self.update_brush_size(value)

        changed, value = imgui.slider_float('Trimap transparency', self._trimap_transparency, 0, 1)
        if changed:
            self._trimap_transparency = value
            self._blended_image = self._image * (
                        1.0 - self._trimap_transparency) + self._trimap * self._trimap_transparency
            self._blended_image = self._blended_image.astype(np.uint8)
            update_texture(self._image_texture_id[0], pyglet.gl.GL_RGB,
                           self._width, self._height, self._blended_image.tobytes())
        imgui.end()

        pyglet.gl.glClearColor(0., 0., 0., 0)
        pyglet.gl.glClear(pyglet.gl.GL_COLOR_BUFFER_BIT)
        imgui.render()
        self.renderer.render(imgui.get_draw_data())


def main():
    director.init(width=800, height=600, resizable=True)

    imgui.create_context()

    hello_layer = HelloWorld()

    main_scene = cocos.scene.Scene(hello_layer)
    director.run(main_scene)


if __name__ == "__main__":
    main()
