# Media GeoTag Mapper (MGTM):
## A Python tool for retrieving, storing, and viewing image and video geotags

By Kenneth Burchfiel

Released under the MIT license

Initially released in 2022; updated extensively in 2026

GitHub link: https://github.com/kburchfiel/media_geotag_mapper

Related blog post (with commentary on some of the maps created within the tutorial notebook):
https://kburchfiel3.wordpress.com/2022/05/10/using-media-geotag-mapper-mgtm-to-visualize-my-travels-over-the-past-10-years/

![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/sample_output.gif)

(The video on which this GIF was based can be found within the project directory as [sample_output.mp4](https://github.com/kburchfiel/media_geotag_mapper/blob/master/sample_output.mp4).)

### Introduction
Media GeoTag Mapper allows you to extract geotag data (e.g. geographical coordinates) from image and video files on your computer, then create maps based on that data. In doing so, it lets you see all the places you've traveled--provided that you took a geotagged image or video clip there.

The maps created by Media GeoTag mapper are in HTML form and interactive in nature. You can pan and zoom them to get a closer look, and by hovering over markers, you can see the geographic coordinates and image creation times for each marker. In addition, clicking on a marker reveals the path to the original file. In addition, the project contains code for converting these HTML maps to both high-quality .png files and lower-sized .jpg files (some of which are shown below). 

So far, I've tested out this code on Samsung, Sony, and Apple devices using a Windows computer. The code that extracts geotag data from images and videos may need to be tweaked in order to work with other devices.

### Examples

Here are two maps of thousands of geotagged images and video clips that I've taken since 2012:

US-centric view:
![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/smaller_screenshots/combined_routes_locations.jpg)

Global view:
![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/smaller_screenshots/combined_routes_intl_locations.jpg)

If you don't want to see the paths in between geotags, you can also create maps of just the geotag locations:
![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/smaller_screenshots/combined_locations.jpg)


It's also interesting to generate maps for each year. For instance, in 2013, you can see that I spent lots of time in Vermont and Virginia:
![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/smaller_screenshots/2013_combined_locations.jpg)


Meanwhile, in 2015, many of my trips originated from Houston:
![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/smaller_screenshots/2015_combined_locations.jpg)

And in 2021, most of my travels were focused on the East Coast:
![](https://raw.githubusercontent.com/kburchfiel/media_geotag_mapper/master/smaller_screenshots/2021_combined_locations.jpg)

### Project files

**media_geotag_functions_v6.py** (or a later version) contains the core functions used within Media Geotag Mapper.

**media_geotag_mapper_tutorial_v14** (or a later version) demonstrates how to use the functions in media_geotag_functions.py to retrieve, store, and map geotag data for photos and videos. 

Two interactive HTML maps created within the media_geotag_mapper_tutorial notebook can be found within the **maps** folder. These maps are interactive, so by downloading them, you can retrieve more information about each marker by hovering over them and by clicking them. You can also pan and zoom each map.

Meanwhile, the **map_screenshots** folder contains screenshots of many more maps generated within the media_geotag_mapper_tutorial notebook (though I excluded these from the Git repository), and the **smaller_screenshots** folder contains .jpg versions of these screenshots with a lower file size.

**df_media_israel.csv** and **df_locations_israel.csv** show samples of the media and locations DataFrames created within the media_geotag_mapper_tutorial notebook. 

### Special thanks

I am grateful to the developers of the [exif-py](https://github.com/ianare/exif-py) and [ffmpeg-python](https://github.com/kkroening/ffmpeg-python) libraries, which this script relies on heavily in order to process image and video metadata. These are just two of the many libraries (Folium, Selenium, etc.) that this script utilizes.