## Media GeoTag Mapper Functions:
# A set of functions for retrieving and mapping geotags 
# (e.g. geographic coordinates) within photos and videos

# By Kenneth Burchfiel

# Released under the MIT License

# GitHub link:
# https://github.com/kburchfiel/media_geotag_mapper

# To see many of these functions in action, look through
# the media_geotag_mapper_tutorial Jupyter Notebook. 

from exif import Image
from os.path import join
import time
# https://exif.readthedocs.io/en/latest/usage.html
# Important warning from the exif library:
# "Back up your photos before using this tool! You are responsible for
# any unexpected data loss that may occur through improper use of this 
# package."
from pyproj import Geod
import numpy as np
import ffmpeg
from tqdm import tqdm
import os
import pandas as pd
import folium
from haversine import haversine, Unit
import datetime
import matplotlib.pyplot as plt
from selenium import webdriver
import PIL.Image

def generate_media_list(top_folder_list, folder_name):
    '''This function goes through all folders contained
    within top_folder_list, then generates a DataFrame with information 
    on the files that it finds within those folders.

    Note: if you receive an AttributeError message that states: 
    'Can only use .str accessor with string values!', 
    make sure that your drive containing your media files 
    is connected to your computer.'''
    file_list = []
    name_list = []
    for top_folder in top_folder_list:
        for root, dirs, files in os.walk(top_folder): 
            # This code is based on:
            # https://docs.python.org/3/library/os.html
            file_list.extend([join(root, name) for name in files])
            # Different copies of 'files' will exist if top_folder_list 
            # contains additional folders, so it's necessary to retrieve 
            # the file names within each of them.
            name_list.extend([name for name in files])
            # For documentation on list.extend, see:
            # (https://docs.python.org/3/tutorial/datastructures.html)
    df_media = pd.DataFrame({'path':file_list, 'name':name_list})
    # df_media is initialized with just file paths and file names.

    path_column = df_media.columns.get_loc('path')
    ctime_list = []
    mtime_list = []
    atime_list = []
    megabytes_list = []
    # The following for loop iterates through each row within
    # df_media and extracts data about file creation/modification/access
    # times, along with each file's size. It then stores this data into
    # new lists that will get added to df_media.
    # See https://docs.python.org/3/library/os.html#os.stat
    # for documentation on the following attributes.
    for i in range(len(df_media)):
        file_stats = os.stat(df_media.iloc[i, path_column])
        ctime_list.append(time.ctime(file_stats.st_ctime))
        # st_ctime, st_mtime, and st_atime are all represented in seconds since
        # the start of the Unix epoch. Therefore, time.ctime is used to convert
        # these values to human-interpretable times.
        mtime_list.append(time.ctime(file_stats.st_mtime))
        # I found that st_mtime (which represents the date that a file
        # was modified) was a more accurate representation of a file's creation
        # date than st_ctime.
        atime_list.append(time.ctime(file_stats.st_atime))
        megabytes_list.append(file_stats.st_size/1000000)
        # st_size represents the size of the file in bytes,
        # so I divide that value by 1 million here in order 
        # to retrieve the size in megabytes.

    df_media['ctime'] = pd.to_datetime(ctime_list)
    # st_ctime, whose values are stored within ctime_list, 
    # refers to the creation time on Windows, whereas
    # on Unix, this refers to "the time of most recent
    # metadata change." However, I found on Windows that st_mtime was a 
    # better representation of the time a video/image was originally captured
    # than was st_ctime.
    # (Source:
    # https://docs.python.org/3/library/os.html#os.stat)
    df_media['modified_time'] = pd.to_datetime(mtime_list)
    df_media['accessed_time'] = pd.to_datetime(atime_list)
    df_media['megabytes'] = megabytes_list

    df_media['extension'] = df_media['name'].str.split('.').str[-1].str.lower()
    # The above line assumes that the last entry within the list created
    # by splitting the 'name' value by peridos will be the file extension.
    # This code should still work if there are periods in the file name
    # (although I try to avoid that practice).

    # Depending on your device type, you wil probably need to update 
    # the following lists to include alternate video and image file types.

    clip_extensions = ['mp4', 'mov', 'mts']
    pic_extensions = ['jpg', 'tiff', 'png', 'jpeg', 'gif']
    # The following use of if/else within a lambda function is based on
    # an example by Professor Hardeep Johar.
    df_media['type'] = df_media['extension'].apply(
    lambda x: 'clip' if x in clip_extensions 
    else 'pic' if x in pic_extensions else 'other')
    # See also:
    # https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.apply.html
    df_media.to_csv(f'{folder_name}_media_list.csv', index = False)
    return df_media

def retrieve_pic_locations(df_pics):
    ''' This function retrieves the geotag (geographic coordinate)
    data from a list of pictures. It assumes that the column names
    are the same as those created within generate_media_list.

    I have tested out this function with image files from both Samsung
    and Apple phones, but some tweaking may be needed in order to get it 
    to work on other devices. If you have an iPhone, 
    consider sorting the output of this function by 
    the 'alt_capture_time' column, which may lead to more accurate paths
    than the 'modified_date' column (which worked well with the Samsung
    media on which I originally tested the function).
    '''
    photo_location_lat_list = []
    photo_location_lon_list = []
    alt_capture_time_list = []
    path_column = df_pics.columns.get_loc('path')
    for i in tqdm(range(len(df_pics))):
        # tqdm creates a handy progress bar for for loops. See
        # https://tqdm.github.io/
        # There are two try/except statements nested within another 
        # try/except statement below. This method allows the function
        # to only try to generate current_image once, thus saving time.
        try:
            with open(df_pics.iloc[i,path_column], 'rb') as image_file:
                current_image = Image(image_file)

            try:          

                # Based on https://pypi.org/project/exif/

                lat_tuple = current_image.gps_latitude
                lat_ref = current_image.gps_latitude_ref
                # lat_tuple contains 3 numbers representing the 
                # degrees, minutes, and seconds that make up the
                # latitude coordinate, and lat_ref contains either
                # 'N' (for North) or 'S' (for South). lon_tuple
                # and lon_ref have similar formats. 

                lon_tuple = current_image.gps_longitude
                lon_ref = current_image.gps_longitude_ref


                # The following code converts these degree/minute/second
                # values into decimal degrees in order to make plotting
                # them easier.
                decimal_lat = lat_tuple[0] + lat_tuple[1]/60 + lat_tuple[2]/3600
                if lat_ref == 'S':
                    decimal_lat *= -1
                
                decimal_lon = lon_tuple[0] + lon_tuple[1]/60 + lon_tuple[2]/3600
                if lon_ref == 'W':
                    decimal_lon *= -1
                
                photo_location_lat_list.append(decimal_lat)
                photo_location_lon_list.append(decimal_lon)


            # If no geotag data is found, the file will be assigned
            # coordinates of 0, 0 that the mapping code will then
            # exclude.
            except:
                photo_location_lat_list.append(0)
                photo_location_lon_list.append(0)

            # The following try/except statement searches for a 'datetime'
            # value within the EXIF data. On the iPhone media on which
            # I tested this function, this datetime value had colons separating
            # the year, month, and date. Therefore, in order to get Pandas to 
            # convert into a Pandas DateTime value, I first needed to
            # relpace the first two colons in the datetime value
            # with hyphens (hence the replace() call below).
            try:
                alt_capture_time_list.append(pd.to_datetime(
                current_image.datetime.replace(':','-', 2)))
            except:
                alt_capture_time_list.append('x')
        
        except:
            photo_location_lat_list.append(decimal_lat)
            photo_location_lon_list.append(decimal_lon)
            alt_capture_time_list.append('x')

    # The function will next add columns with this coordinate data
    # to df_pics.
    df_pics['raw_location'] = 0 # This won't be used for the pics column, but 
    # is added in so that the columns of both df_pics and df_clips will match.
    df_pics['lat'] = photo_location_lat_list
    df_pics['lat'] = pd.to_numeric(df_pics['lat'])
    df_pics['lon'] = photo_location_lon_list
    df_pics['lon'] = pd.to_numeric(df_pics['lon'])
    df_pics['alt_capture_time'] = alt_capture_time_list
    return df_pics


def retrieve_clip_locations(df_clips):
    ''' This function retrieves the geotag (geographic coordinate)
    data from a list of images. It assumes that the column names
    are the same as those created within generate_media_list.
    I have tested out this function with video files from both Samsung
    and Apple phones, but some tweaking may be needed in order to get it 
    to work on other devices. If you have an iPhone, 
    consider sorting the output of this function by 
    the 'alt_capture_time' column, which may lead to more accurate paths
    than the 'modified_date' column (which worked well with the Samsung
    media on which I originally tested the function).

    '''
    video_location_list = []
    alt_capture_time_list = []
    path_column = df_clips.columns.get_loc('path')
    for i in tqdm(range(len(df_clips))):

        # There are two try/except statements nested within another 
        # try/except statement below. This method allows the function
        # to only try to generate current_image once, thus saving time.
        try:
            metadata = ffmpeg.probe(df_clips.iloc[i, path_column])
            # Based on https://kkroening.github.io/ffmpeg-python/#ffmpeg.probe
            # The metadata dictionary for each video clip contains many
            # different components, so it's necessary to search through
            # the dictionary in order to retrieve the video location. 

            try:
                # I found iPhone video geotag data to be stored within
                # a 'com.apple.quicktime.location.ISO6709' key, whereas
                # Samsung video location data was stored within a 'location'
                # key, hence this if/else statement. Other devices may use
                # other keys.
                if 'location' in metadata['format']['tags'].keys():
                    video_location_list.append(
                        metadata['format']['tags']['location'])
                elif 'com.apple.quicktime.location.ISO6709' in metadata[
                'format']['tags'].keys():
                    video_location_list.append(
                        metadata['format']['tags'][
                        'com.apple.quicktime.location.ISO6709'])
                else:
                    video_location_list.append('xxxxxxxxxxxxxxxxx')
            # This 'location' value, at least for the videos on my Samsung 
            # Galaxy S21 Ultra, consists of 17 characters that will then 
            # get split into a latitude and longitude component below.
            # Therefore, if no location data is present, the following
            # 'except' clause creates a set of 17 x values that can still be
            # split into two parts.

            except:
                video_location_list.append('xxxxxxxxxxxxxxxxx')


            # The following try/except statement searches for a 
            # 'com.apple.quicktime.creationdate' value within the video
            # metadata. I imagine this value will only be present within 
            # Apple devices.
 
            try:
                if 'com.apple.quicktime.creationdate' in metadata[
                    'format']['tags'].keys():
                    alt_capture_time_list.append(
                    pd.to_datetime(metadata[
                        'format']['tags']['com.apple.quicktime.creationdate']))
                else:
                    alt_capture_time_list.append('x')
            except:
                alt_capture_time_list.append('x')
        except:
            video_location_list.append('xxxxxxxxxxxxxxxxx')
            alt_capture_time_list.append('x')

    
    df_clips['alt_capture_time'] = alt_capture_time_list
    df_clips['raw_location'] = video_location_list
    # The first 8 characters within 'raw_location' contain latitude data, 
    # so they will be stored within df_clips['lat'].
    df_clips['lat'] = df_clips['raw_location'].str[0:8]
    # The next 9 characters contain longitude data, so they'll be stored
    # # within df_clips['lon']. 
    df_clips['lon'] = df_clips['raw_location'].str[8:17]
    # There may also be elevation data present depending on your device,
    # but this version of the code doesn't make use of that data.

    # Now that the entries with missing geographic coordinates have been
    # separated into latitude and longitude components, they can be converted
    # to 0 so that the subsequent pd.to_numeric function will work.

    df_clips['lat'] = df_clips['lat'].str.replace('xxxxxxxx', '0')
    df_clips['lon'] = df_clips['lon'].str.replace('xxxxxxxxx', '0')
    
    df_clips['lat'] = pd.to_numeric(df_clips['lat'])
    df_clips['lon'] = pd.to_numeric(df_clips['lon'])
    return df_clips
    


def generate_loc_list(df_media, folder_name):
    ''' This function takes a DataFrame formatted like those returned
    via generate_media_list, then calls retrieve_pic_locations and 
    retrieve_clip locations in order to obtain those files' geographic
    coordinates. 
    '''
    # The function first splits df_media into video (df_clips) and picture
    # (df_pics) DataFrames, since the process of retrieving coordinate 
    # data differs for those two media types.
    df_clips = df_media.query("type == 'clip'").copy()
    df_pics = df_media.query("type == 'pic'").copy()
    print("Retrieving picture locations:")
    df_pic_locs = retrieve_pic_locations(df_pics)
    print("Retrieving clip locations:")
    df_clip_locs = retrieve_clip_locations(df_clips)
    # Once coordinate data has been retrieved for both df_clips and df_pics,
    # the DataFrames containing this coordinate data (df_clip_locs and 
    # df_pic_locs) can be merged back together.
    df_media_locs = pd.concat([df_pic_locs, df_clip_locs])
    df_media_locs.to_csv(f'{folder_name}_media_locations.csv', index = False)
    return df_media_locs


def map_media_locations(df_locations, file_name, folder_path = None, 
add_paths = False, starting_location = [39, -95], zoom_start = 4, 
timestamp_column = 'modified_time', longitude_cutoff = 80, 
marker_type = 'CircleMarker', circle_marker_color = '#ff0000', radius = 5, 
path_color = '#3388ff', path_weight = 3, tiles = 'OpenStreetMap'):
    '''map_media_locations converts lists of files and geographic coordinates
    into maps of those coordinates. It also displays the media creation time
    and geographic coordinates when the user hovers over a map tile. 
    Furthermore, when the user clicks on a map tile, the original file path 
    will appear.
    
    Variable explanations:

    df_locations: The DataFrame containing file and geotag data. It's assumed
    that this DataFrame will have been generated using the generate_loc_list
    function.

    file_name: The name that should be used when saving the final map.
    The function adds '_locations' to this map name.

    folder_path: The path into which the map file should be saved. If 
    kept as 'None,' the map will be saved within the project's root folder.

    add_paths: If set to True, map_media_locations will add paths in between
    each point on the map. For this to work correctly, it's important that 
    the points are sorted in chronological order; otherwise, the paths
    added in won't reflect your actual travels.

    starting_location: The starting geographic coordinates of the Folium
    map, represented as a list of [latitude, longitude] values in decimal
    degree form.

    zoom_start: A value reflecting the zoom level of the Folium map. The higher
    the value, the more zoomed in the map will be.

    timestamp_column: The column within the DataFrame that contains the time
    that each image/video was created. I found that, for Samsung media,
    the 'modified_date' column created in the generate_media_list function
    best represented this time, whereas for iPhone media, the
    'alt_capture_time' column created within the generate_loc_list function
    worked better.

    longitude_cutoff: Longitude points above this value will be reduced by 
    360. This cutoff prevents the map from drawing incorrect paths between
    points.
    For instance, without this cutoff, if the map tried to plot a path
    between Alaska and Japan, it would draw the line eastward across
    North America, the Atlantic, Europe, and Asia. However, with a
    longitude_cutoff value of 80, the longitude value of the Japanese 
    coordinate will be reduced so that the coordinate appears to the left
    of the Alaska coordinate. This will result in a path drawn across
    the Pacific.
    The default value of 80 is 'Americentric,' so if your points instead
    originate from Europe or Asia, you'll probably need to update this value.

    marker_type: This can be either 'Marker' or 'CircleMarker.' I prefer
    'CircleMarker' because the points can be resized to better accommodate
    large datasets.

    circle_marker_color: The color that will be assigned to any 
    CircleMarkers on the map. 

    radius: The radius of the CircleMarkers.

    tiles: The map tile type to use.

    path_color: The color to use when drawing paths in between points.
    The default color comes from:
    https://python-visualization.github.io/folium/modules.html#folium.vector_layers.path_options

    path_weight: The weight (thickness) of the paths.


    '''
    m = folium.Map(location = starting_location, zoom_start = zoom_start, 
    tiles = tiles)
    locations_to_map = df_locations.query("lat != 0 & lon != 0").copy()
    # The above line removes any 'Null Island' geotags from the map.

    lat_column = locations_to_map.columns.get_loc('lat')
    lon_column = locations_to_map.columns.get_loc('lon')
    timestamp_column = locations_to_map.columns.get_loc(timestamp_column)
    file_path_column = locations_to_map.columns.get_loc('path')
    stroke_opacity = radius/5 # If CircleMarkers will be used to show the
    # geotags, then the stroke value will be one fifth of the radius value.
    name_column = locations_to_map.columns.get_loc('name')

    marker_count = 0


    if add_paths == True:
        g = Geod(ellps="WGS84")
        # From https://pyproj4.github.io/pyproj/stable/api/geod.html

        # The following for loop adds lines in between
        # different points on the map. This loop runs first
        # so that the lines won't appear on top of the markers.

        # This loop creates lines by generating a series of points that can 
        # be plotted on the map. A simple solution would be to simply draw a 
        # straight line in between the two points. However, this has two issues:
        # 1. The paths between far-apart points are influenced by the curvature
        # of the Earth, so plotting linear lines would be unrealistic.
        # 2. US-to-East-Asia paths would be plotted eastbound rather than 
        # westbound, which is extremely unrealistic.
        # Therefore, the following set of code uses the pyproj library to create
        # great circle paths (e.g. paths that curve along with the Earth)
        # to better represent the actual paths between points. This may also
        # make it easier to plot trans-Pacific paths.
        # However, Folium cuts off lines once they hit the international 
        # date line. To resolve this issue, I needed to create a new cutoff
        # point ('longitude_cutoff') and then subtract 360 from 
        # longitude values that exceeded these coordinates. This ensured 
        # that paths east of this point (e.g. places east of Central India) 
        # would appear on the left of the map rather than on the right.

        for i in range(1, len(locations_to_map)):
            # To plot lines between points, the function first obtains 
            # the geographic coordinates of the current row and 
            # the previous row (which is why it's crucial for the DataFrame
            # passed to this function to have the points in the correct order). 
            lat = locations_to_map.iloc[i, lat_column]
            lon = locations_to_map.iloc[i, lon_column]

            prev_lat = locations_to_map.iloc[
                i-1, locations_to_map.columns.get_loc('lat')]           
            prev_lon = locations_to_map.iloc[
                i -1, locations_to_map.columns.get_loc('lon')]

            if (lat == prev_lat) & (lon == prev_lon):
                continue # If this row's points are the same as the last row's,
                # there's no need to attempt to draw a line between them.
            if lon > longitude_cutoff: # See above for explanation
                mapped_lon = lon - 360
            else:
                mapped_lon = lon
        # This method of reducing far-east longitude points by 360 is based on
        # the response by 'mourner' at:
        # https://github.com/Leaflet/Leaflet/issues/82#issuecomment-1260488


            if prev_lon > longitude_cutoff:
                mapped_prev_lon = prev_lon - 360
            else:
                mapped_prev_lon = prev_lon


        # The following code uses pyproj to create a list of
        # great circle ('gc') points
        # that produce curvilinear paths, which are both more accurate
        # and more aesthetically pleasing than straight paths. From:
        # https://pyproj4.github.io/pyproj/stable/api/geod.html?highlight=npts#pyproj.Geod.npts

            gc_points = g.npts(mapped_prev_lon, prev_lat,
                mapped_lon, lat, 20, initial_idx = 0, terminus_idx = 0)
                # Creates 20 points for each line
                # See documentation at:
                # https://pyproj4.github.io/pyproj/stable/api/geod.html

            flipped_gc_points = ([(coords[1], coords[0]-360) 
            if coords[0] > longitude_cutoff else (coords[1], coords[0])
            for coords in gc_points]) 
 
            # # The coordinates in gc_points are stored in (longitude, latitude)
            # format, so the above list comprehension flips them back into
            # (latitude, longitude) format for plotting. It also modifies
            # points above the longitude cutoff so that they appear on the
            # right side of the map, resulting in more accurate paths.
          
            folium.PolyLine(flipped_gc_points, color = path_color,
            weight = path_weight).add_to(m) 

    # Now that all paths (if requested) have been added to the map, the code
    # will now add points 

    for i in range(len(locations_to_map)):
        lat = locations_to_map.iloc[i, lat_column]
        lon = locations_to_map.iloc[i, lon_column]
        if lon > longitude_cutoff:
            mapped_lon = lon - 360
        else:
            mapped_lon = lon
        timestamp = locations_to_map.iloc[i, timestamp_column]
        tooltip = str(timestamp) + ': ' + str(lat)+', '+str(lon)
        file_path = locations_to_map.iloc[i, file_path_column]
        # I found that popup values with backslashes would prevent the maps
        # from displaying correctly, perhaps because it modifies the 
        # HTML code underlying the maps. Therefore, the following line replaces
        # any backslashes in the file paths with forward slashes.
        modified_fp = file_path.replace('\\', '/')
        # name = locations_to_map.iloc[i, name_column] # You may choose
        # to display the name instead of the file path instead.
        # The following try block attempts to add markers to the map. If 
        # this is unsuccessful, it will instead continue to the next line
        # within the function.
        try:
            if marker_type == 'CircleMarker':
                folium.CircleMarker([lat,mapped_lon],
                color = '#000000',
                radius = radius,
                weight = 0.5,
                opacity = stroke_opacity,
                fill_color = circle_marker_color,
                fill_opacity = 1.0,
                tooltip = tooltip,
                popup = modified_fp).add_to(m)
            else:
                folium.Marker([lat,mapped_lon],
                tooltip = tooltip,
                popup = modified_fp).add_to(m)

            # See https://python-visualization.github.io/folium/modules.html#folium.vector_layers.path_options
            # for different path options
            marker_count += 1

        except:
            continue

    print("Added",marker_count,"markers to the map.")

    # Finally, the function will save the map in the location specified.
    if folder_path != None:
        m.save(f'{folder_path}/{file_name}_locations.html')
    else:
        m.save(f'{file_name}_locations.html')
    return m


def folder_list_to_map(top_folder_list, file_name, folder_path = None):
    ''' This function calls generate_media_list, generate_loc_list,
    and map_media_locations together in order to turn a list of folders
    into a map.
    '''
    df_media = generate_media_list(top_folder_list = top_folder_list, 
    file_name = file_name)
    # generate_media_list saves the output as a .csv
    df_locations = generate_loc_list(df_media = df_media, 
    file_name = file_name)
    # generate_loc_list also saves the output as a .csv
    location_map = map_media_locations(df_locations = df_locations, 
    file_name = file_name, folder_path = folder_path)
    # map_media_locations saves the output as an .html file
    return(location_map)


def flip_lon(df, lat_south_bound, lat_north_bound, 
lon_west_bound, lon_east_bound):
    '''This function flips the bearing of longitude values within the area
    demarcated by lat_south_bound, lat_north_bound, lon_west_bound, and 
    lon_east_bound. I created this function because I found that some of 
    my geotags had an incorrect orientation (e.g. East instead of West). 
    This function assumes that all longitude values within the demarcated
    area need to be flipped, which may not be accurate in your case.
    '''
    df['lon'] = df.apply(lambda row: row['lon']*-1 if 
    (row['lat'] > lat_south_bound) & (row['lat'] < lat_north_bound) & 
    (row['lon'] > lon_west_bound) & (row['lon'] < lon_east_bound) 
    else row['lon'], axis = 1)
    return df

def create_map_screenshot(absolute_path_to_map_folder, map_name, 
screenshot_save_path = None):

    '''
    This function uses the Selenium library to create a screenshot 
    of a map so that it can be shared as a .png file.
    See https://www.selenium.dev/documentation/ for more information on 
    Selenium. 
    
    absolute_path_to_map_folder designates the absolute path where
    the map is stored. (I wasn't able to get this code to work using
    just relative paths.) 

    map_name specifies the name of the map, including its extension.

    screenshot_save_path designates the folder where you wish to save
    the map screenshot. This can be a relative path.

    Note that some setup work is required for the Selenium code
    to run correctly; if you don't have time right now to complete this 
    setup, you can comment out any code that calls this function.
    '''

    ff_driver = webdriver.Firefox() 
    # See https://www.selenium.dev/documentation/webdriver/getting_started/open_browser/
    # For more information on using Selenium to get screenshots of .html 
    # files, see my get_screenshots.ipynb file within my route_maps_builder
    # program, available here:
    # https://github.com/kburchfiel/route_maps_builder/blob/master/get_screenshots.ipynb
    window_width = 3000 # This produces a large window that can better
    # capture small details (such as zip code shapefiles).
    ff_driver.set_window_size(window_width,window_width*(9/16)) # Creates
    # a window with an HD/4K/8K aspect ratio
    ff_driver.get(f'{absolute_path_to_map_folder}\\{map_name}') 
    # See https://www.selenium.dev/documentation/webdriver/browser/navigation/
    time.sleep(2) # This gives the page sufficient
    # time to load the map tiles before the screenshot is taken. 
    # You can also experiment with longer sleep times.

    if screenshot_save_path != None:
        # If specifying a screenshot save path, you must create this path
        # within your directory before the function is run; otherwise,
        # it won't return an image. 
        ff_driver.get_screenshot_as_file(
            screenshot_save_path+'/'+map_name.replace('.html','')+'.png') 
    else: # If no save path was specified for the screenshot, the image
        # will be saved within the project's root folder.
        ff_driver.get_screenshot_as_file(
            map_name.replace('.html','')+'.png') 
    # Based on:
    # https://www.selenium.dev/selenium/docs/api/java/org/openqa/selenium/TakesScreenshot.html

    ff_driver.quit()
    # Based on: https://www.selenium.dev/documentation/webdriver/browser/windows/

def batch_create_map_screenshots(absolute_path_to_map_folder, 
screenshot_save_path = None):
    '''This function
    applies create_map_screenshot to all files within a folder. It assumes
    that the folder contains only image files.'''
    for root, dirs, files in os.walk(absolute_path_to_map_folder):
        maps_list = files
    for map in maps_list:
        create_map_screenshot(absolute_path_to_map_folder, 
        map_name = map, screenshot_save_path = screenshot_save_path)

def convert_png_to_smaller_jpg(png_folder, png_image_name, jpg_folder, 
reduction_factor = 1, quality_factor = 50):
    ''' This function converts a .png image into a smaller .jpg image, which
    helps reduce file sizes and load times when displaying a series of images
    within a notebook or online.
    png_folder and png_image_name specify the location of the original .png
    image.
    jpg folder specifies the location where the .jpg screenshot should be
    saved.
    reduction_factor specifies the amount by which you would like to reduce
    the image's dimensions. For instance, to convert a 4K (3840*2160) image
    to a full HD (1920*1080) one, use a reduction factor of 2. If you do not
    wish to reduce the image's size, use the default reduction factor of 1.
    '''
    with PIL.Image.open(f'{png_folder}/{png_image_name}') as map_image:
        (width, height) = (map_image.width // reduction_factor, 
        map_image.height // reduction_factor)
        jpg_image = map_image.resize((width, height))
        # The above code is based on:
        # https://pillow.readthedocs.io/en/stable/reference/Image.html
        jpg_image = jpg_image.convert('RGB')
        # The above conversion is necessary in order to save .png files as 
        # .jpg files. It's based on Patrick Artner's answer at: 
        # https://stackoverflow.com/a/48248432/13097194
        jpg_image_name = png_image_name.replace('png', 'jpg') 
        jpg_image.save(f'{jpg_folder}/{jpg_image_name}',
        format = 'JPEG', quality = quality_factor, optimize = True)
        # See https://pillow.readthedocs.io/en/stable/handbook/image-file-formats.html#jpeg

def batch_convert_pngs_to_smaller_jpgs(png_folder, jpg_folder, 
reduction_factor, quality_factor):
    '''This function converts all items within a given folder into
    .png files. It assumes that all of the files within the folder are
    .png image files. (For this reason, I strongly recommend using different
    folders for the png_folder and jpg_folder arguments.)
    '''
    for root, dirs, files in os.walk(png_folder):
        png_image_list = files
    for png_image_name in png_image_list:
        convert_png_to_smaller_jpg(png_folder, png_image_name, jpg_folder,
        reduction_factor, quality_factor)

def calculate_distance_by_year(df_locations, unit = 'miles', 
    timestamp_column = 'modified_time'):
    '''This function uses the geographic coordinate information within
    df_locations to estimate how far you've traveled each year. It assumes
    that the rows in df_locations are sorted in chronological order. 
    Otherwise, it will likely overestimate your travel distance by a large
    extent.'''
    df = df_locations.copy()
    df['distance'] = 0
    lat_col = df.columns.get_loc('lat')
    lon_col = df.columns.get_loc('lon')
    dist_col = df.columns.get_loc('distance')
    for i in range(1, len(df)):
        prev_pt = (df.iloc[i-1, lat_col], 
        df.iloc[i-1, lon_col])
        cur_pt = (df.iloc[i, lat_col], 
        df.iloc[i, lon_col])
        if unit == 'miles':
            df.iloc[i, dist_col] = haversine(prev_pt, cur_pt,
            unit = Unit.MILES)
            # haversine() calculates the haversine (great-circle) 
            # distance in between two points, which is more accurate 
            # for a spherical surface like the world 
            # than is the Euclidean distance.
        else:
            if unit != 'kilometers':
                print("This function supports miles and kilometers for units. \
Using kilometers as the distance measure.")
            df.iloc[i, dist_col] = haversine(prev_pt, cur_pt) # Calculates
            # distance values in kilometers

    # The function will now calculate the total distance traveled 
    # for each year.
    df['year'] = df[timestamp_column].dt.to_period('Y')
    # See:
    # https://pandas.pydata.org/docs/reference/api/pandas.Series.dt.to_period.html
    df_stats_by_year = df.pivot_table(index='year', values=[
        'distance', 'lat'], aggfunc = {
            'distance':'sum', 'lat':'count'}) 
    # See:
    # https://pandas.pydata.org/docs/reference/api/pandas.pivot_table.html
    df_stats_by_year.rename(columns={'lat':'geotags',
    'distance':'total_distance'}, inplace = True)
    df_stats_by_year.reset_index(inplace=True)
    return df_stats_by_year