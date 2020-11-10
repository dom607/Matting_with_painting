from __future__ import absolute_import

import cocos
from cocos.director import director

import pyglet
import pygame

from imgui.integrations.cocos2d import ImguiLayer
import imgui
import numpy as np
import math
import itertools
from enum import Enum

import os
import sys
path = os.path.abspath('FBA_MATTING')
if path not in sys.path:
    sys.path.append(path)
from FBA_Matting.demo import pred
import matplotlib.pyplot as plt

# TODO:
# 1. Using imgui.ini


class Color(Enum):
    FOREGROUND = [255, 255, 255, 255]
    BACKGROUND = [0, 0, 0, 255]
    UNKNOWN = [127, 127, 127, 255]
    UNDEFINED = [0, 0, 0, 0]


class HelloWorld(ImguiLayer):
    is_event_handler = True

    def __init__(self):
        super(HelloWorld, self).__init__()

        self._text = "Input text here"
        self._drag_start_pos = []
        self._prev_mouse_pos = []
        self._brush_radius = 3  # pixel
        self._brush_color = Color.FOREGROUND
        self._image_window_size = [400, 400]  # Load from imgui.ini

        self._image = pygame.image.load('03005.png')
        texture_surface = pygame.transform.flip(self._image, False, True)
        texture_data = pygame.image.tostring(texture_surface, "RGBA", 1)

        self._width = texture_surface.get_width()
        self._height = texture_surface.get_height()
        self._trimap = np.zeros((self._height, self._width, 4)).astype(np.uint8)
        self._trimap_update_history = []  # Store points information for undo, redo.

        # for y in range(self._height):
        #     self._trimap[y, :, 2] = int(y / self._height * 255)

        self._trimap = self._trimap.astype(np.uint8)

        # Create image texture
        self._image_texture_id = (pyglet.gl.GLuint * 1)()
        pyglet.gl.glGenTextures(1, self._image_texture_id)
        pyglet.gl.glBindTexture(pyglet.gl.GL_TEXTURE_2D, self._image_texture_id[0])
        pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MAG_FILTER, pyglet.gl.GL_LINEAR)
        pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MIN_FILTER, pyglet.gl.GL_LINEAR)
        pyglet.gl.glTexImage2D(pyglet.gl.GL_TEXTURE_2D, 0, pyglet.gl.GL_RGBA, self._width, self._height, 0,
                               pyglet.gl.GL_RGBA, pyglet.gl.GL_UNSIGNED_BYTE, texture_data)

        # Create trimap texture
        self._trimap_image_texture_id = (pyglet.gl.GLuint * 1)()
        pyglet.gl.glGenTextures(1, self._trimap_image_texture_id)
        pyglet.gl.glBindTexture(pyglet.gl.GL_TEXTURE_2D, self._trimap_image_texture_id[0])
        pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MAG_FILTER, pyglet.gl.GL_LINEAR)
        pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MIN_FILTER, pyglet.gl.GL_LINEAR)
        pyglet.gl.glTexImage2D(pyglet.gl.GL_TEXTURE_2D, 0, pyglet.gl.GL_RGBA, self._width, self._height, 0,
                               pyglet.gl.GL_RGBA, pyglet.gl.GL_UNSIGNED_BYTE, self._trimap.tobytes())

        # Generate displacement table
        self._displacement_table = []
        self.update_brush_size(5)

    def update_brush_size(self, brush_radius):
        self._brush_radius = brush_radius

        for displacement_x in range(-self._brush_radius, self._brush_radius + 1):
            for displacement_y in range(-self._brush_radius, self._brush_radius + 1):
                if math.sqrt(displacement_x * displacement_x + displacement_y * displacement_y) <= self._brush_radius:
                    self._displacement_table.append((displacement_x, displacement_y))

    def clear_trimap(self, trimap_color=None):
        if trimap_color == None:
            self._trimap[:, :] = Color.UNDEFINED.value
        else:
            self._trimap[:, :] = trimap_color.value

    # def predict(self):
    #     pred(self._im)

    # TODO : Apply interpolation algorithm.
    def update_trimap(self, current_mouse_pos):

        # List up calculation point
        displacement_x = current_mouse_pos[0] - self._prev_mouse_pos[0]
        displacement_y = current_mouse_pos[1] - self._prev_mouse_pos[1]

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

                self._trimap[int(y + disp_y), int(x + disp_x), :] = self._brush_color.value

        # for i, point in enumerate(points):
        #     if i != 0 and i != len(points) - 1:
        #         continue
        #
        #     x = point[0]
        #     y = point[1]
        #     for displacement in self._displacement_table:
        #         disp_x = displacement[0]
        #         disp_y = displacement[1]
        #
        #         # Check boundaries
        #         if x + disp_x < 0 or x + disp_x >= self._width:
        #             continue
        #
        #         if y + disp_y < 0 or y + disp_y >= self._height:
        #             continue
        #
        #         self._trimap[int(y + disp_y), int(x + disp_x), :] = [255, 0, 0, 255]

        pyglet.gl.glBindTexture(pyglet.gl.GL_TEXTURE_2D, self._trimap_image_texture_id[0])
        pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MAG_FILTER, pyglet.gl.GL_LINEAR)
        pyglet.gl.glTexParameteri(pyglet.gl.GL_TEXTURE_2D, pyglet.gl.GL_TEXTURE_MIN_FILTER, pyglet.gl.GL_LINEAR)
        pyglet.gl.glTexImage2D(pyglet.gl.GL_TEXTURE_2D, 0, pyglet.gl.GL_RGBA, self._width, self._height, 0,
                               pyglet.gl.GL_RGBA, pyglet.gl.GL_UNSIGNED_BYTE, self._trimap.tobytes())

    def draw(self, *args, **kwargs):
        imgui.new_frame()

        if imgui.begin_main_menu_bar():
            if imgui.begin_menu("File", True):

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
        # if imgui.is_window_hovered() and imgui.is_mouse_clicked(2):
        #     imgui.open_popup('Image menu')
        #
        # if imgui.begin_popup('Image menu'):
        #     imgui.text('Menu')
        #     imgui.separator()
        #     if imgui.selectable('Test 0'):
        #         print('Test 0')
        #     if imgui.selectable('Test 1'):
        #         print('Test 1')
        #     imgui.end_popup()

        # Mouse activity
        if imgui.is_mouse_clicked(0) and imgui.is_window_hovered():
            self._drag_start_pos = relative_pos
            self._prev_mouse_pos = relative_pos

        if imgui.is_mouse_dragging(0) and imgui.is_window_hovered():
            displacement_x = relative_pos[0] - self._prev_mouse_pos[0]
            displacement_y = relative_pos[1] - self._prev_mouse_pos[1]

            if displacement_x != 0 or displacement_y != 0:
                self.update_trimap(relative_pos)
            self._prev_mouse_pos = relative_pos

        imgui.image(self._trimap_image_texture_id[0], self._width, self._height)
        current_window_size = imgui.get_window_size()
        self._image_window_size = [current_window_size[0], current_window_size[1]]
        imgui.end()

        ######################################################################

        imgui.begin('Image menu')
        imgui.text('Image menu')
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
