# Simple matting tool
Simple gui matting tool with PyImgui and FBA matting. It was developed on Windows and has not been tested on other platforms.
- pyimgui : https://github.com/swistakm/pyimgui
- FBA matting : https://github.com/MarcoForte/FBA_Matting

# Installation
## PIP dependencies
- pytorch : 1.7.0 is used.
- pyimgui : See the pyimgui page for installation. This project was created using the PyGame renderer.
- opencv
- numpy

## FBA Matting
- It is attached as a submodule.
- Download the pretrained model and place it in the FBA_Matting/pretrained directory.

## Known issue
- Crash often occurs when the file dialog is opened. 
- Performance issues
  - The trimap update is slow when moving fast with a large brush size.
  - If the image size is too large, a CUDA memory allocation error occurs. (e.g. NVIDIA ffhq dataset)
## TODO  
- Save the last position and size of the window to imgui.ini.
- Adding various inference results preview windows. (Foreground, Background)
- Zoom in / out.
- Optimization
  - Change trimap color format change from RGB to GRAY
  - Make trimap update faster. 
  - Display using a blending shader.
  - Optimize the process before and after inference.   
- Update trimap even on mouse click. Currently, it only works when dragging.
- Undo / Redo
- File dialog change.
- Reduce pip dependencies
  - Replace opencv with Pillow.