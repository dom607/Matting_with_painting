import pyglet


def update_texture(texture_id, texture_type, width, height, texture_raw_data):
    pyglet.gl.glBindTexture(pyglet.gl.GL_TEXTURE_2D, texture_id)
    pyglet.gl.glTexImage2D(pyglet.gl.GL_TEXTURE_2D, 0, texture_type, width, height, 0,
                           texture_type, pyglet.gl.GL_UNSIGNED_BYTE, texture_raw_data)