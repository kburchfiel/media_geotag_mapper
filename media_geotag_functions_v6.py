## Media GeoTag Mapper Functions:
# A set of functions for retrieving and mapping geotags 
# (e.g. geographic coordinates) within photos and videos

# By Kenneth Burchfiel

# Released under the MIT License

# GitHub link:
# https://github.com/kburchfiel/media_geotag_mapper

# To see many of these functions in action, look through
# the media_geotag_mapper_tutorial and media_geotag_mapper_iPhone_example Jupyter Notebooks. 

import exifread # Installed via 'pip install exifread'. See
# https://github.com/ianare/exif-py
from os.path import join
import time
from pyproj import Geod
import numpy as np
import ffmpeg
from tqdm import tqdm
import os
import pandas as pd
import folium
from haversine import haversine, Unit
import datetime
from selenium import webdriver
import PIL.Image

def generate_media_list(top_folder_list, folder_name, 
                        files_to_import = 0):
    '''This function goes through all folders contained
    within top_folder_list, then generates a DataFrame with information 
    on the files that it finds within those folders.

    files_to_import: The number of files from each folder (including
    subfolders) that you would like to process. Set to 0 to import
    all files; set to a positive integer to import only that number
    of files (which can be useful for debugging and testing work).

    Note: if you receive an AttributeError message that states: 
    'Can only use .str accessor with string values!', 
    make sure that your drive containing your media files 
    is connected to your computer.
    
    A previous version of this function that saved items as different
    lists took only around 1/3 to 1/4 of the time--but, due to the risk
    of those lists' getting out of sync, I updated the code with this
    slower, but perhaps more reliable, approach.'''

    media_dict_list = []
    for top_folder in top_folder_list:
        for root, dirs, files in os.walk(top_folder): 
            if files_to_import > 0:
                # Limiting the number of files within each subfolder
                # that the program will read (if requested by 
                # the caller):
                files = files[0:int(files_to_import)].copy()
            for file in files: 
                # You can add [0:10] to files to speed
                # up this function while debugging your code
                # This code is based on:
                # https://docs.python.org/3/library/os.html
                path = join(root, file)
                file_stats = os.stat(path)
                # See https://docs.python.org/3/library/os.html#os.stat
                # for documentation on the following attributes.
                ctime = file_stats.st_ctime
                # st_ctime, st_mtime, and st_atime are all represented in seconds since
                # the start of the Unix epoch. Therefore, time.ctime is used to convert
                # these values to human-interpretable times.
                mtime = file_stats.st_mtime
                # I found that st_mtime (which represents the date that a file
                # was modified) was a more accurate representation of a file's creation
                # date than st_ctime. However, it had some notable inaccuracies
                # as well on at least one date; therefore, I updated this file
                # to add in metadata-based file creation times.
                atime = file_stats.st_atime
                megabytes = file_stats.st_size/1000000
                # st_size represents the size of the file in bytes,
                # so I divide that value by 1 million here in order 
                # to retrieve the size in megabytes.

                utc_ctime_estimate = pd.to_datetime(ctime, unit = 's', utc=True)
                # st_ctime, whose values are stored within ctime_list, 
                # refers to the creation time on Windows, whereas
                # on Unix, this refers to "the time of most recent
                # metadata change." However, I found on Windows that st_mtime was a 
                # better representation of the time a video/image was originally captured
                # than was st_ctime.
                # (Source:
                # https://docs.python.org/3/library/os.html#os.stat)
                utc_modified_time_estimate = pd.to_datetime(
                    mtime, unit = 's', utc=True)
                utc_accessed_time_estimate = pd.to_datetime(atime, unit = 's', 
                                                           utc=True)
            
                extension = file.split('.')[-1].lower()
                # The above line assumes that the last entry within the list created
                # by splitting the 'name' value by peridos will be the file extension.
                # This code should still work if there are periods in the file name
                # (although I try to avoid that practice).
            
                # Depending on your device type, you wil probably need to update 
                # the following lists to include alternate video and image file types.
            
                clip_extensions = ['mp4', 'mov', 'mts']
                pic_extensions = ['jpg', 'tiff', 'png', 'jpeg', 'heic']
                # The following use of if/else within a lambda function is based on
                # an example by Professor Hardeep Johar.

                if extension in clip_extensions:
                    file_type = 'clip'
                elif extension in pic_extensions:
                    file_type = 'pic'
                else:
                    file_type = 'other'
                
                media_dict_list.append(
                    {'path':path, 'name':file, 'utc_ctime_estimate':utc_ctime_estimate,
                    'utc_modified_time_estimate':utc_modified_time_estimate,
                    'utc_accessed_time_estimate':utc_accessed_time_estimate,
                    'megabytes':megabytes, 'extension':extension,
                    'type':file_type})

    df_media = pd.DataFrame(media_dict_list)

        
    # https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.apply.html
    df_media.to_csv(f'{folder_name}_media_list.csv', index = False)
    return df_media

def retrieve_pic_locations(df_pics):
    ''' This function retrieves the geotag (geographic coordinate)
    data from a list of pictures. It assumes that the column names
    are the same as those created within generate_media_list.

    I have tested out this function with image files from both Samsung
    and Apple phones, but some tweaking may be needed in order to get it 
    to work on other devices. 
    '''

    # Creating new columns within df_pics that will be filled in with
    # data retrieved within this loop:
    
    df_pics['raw_location'] = 0 # This won't be used for the pics column, but 
    # is added in so that the columns of both df_pics and df_clips will match.
    df_pics['lat'] = 0.0
    df_pics['lon'] = 0.0

    utc_epoch_start = pd.to_datetime(
        0, unit = 's', utc = True)
    df_pics['utc_metadata_creation_time'] = utc_epoch_start  
    # I had initially initialized this column
    # with pd.NaT, but (presumably because that value isn't timezone aware),
    # I would then get errors like the following when filling this column
    # with UTC-based values:
    
    # FutureWarning: Setting an item of incompatible dtype is deprecated 
    # and will raise an error in a future version of pandas. Value 
    # '2012-06-26 00:21:44+00:00' has dtype incompatible with 
    # datetime64[ns], please explicitly cast to a compatible dtype first.

    # Therefore, I'm instead filling this column with a placeholder
    # value that comes right at the beginning of the Unix time epoch.
    # I'll then replace these values with pd.NaT ones after the DataFrame
    # has finished updating.
    
    

    # Determining the location of each of these columns (which will
    # come in handy when adding values to them via .iloc):
    lat_column_position = df_pics.columns.get_loc('lat')
    lon_column_position = df_pics.columns.get_loc('lon')
    utc_metadata_creation_time_position = df_pics.columns.get_loc(
        'utc_metadata_creation_time')
    
    for i in tqdm(range(len(df_pics))):
        path = df_pics.iloc[i]['path']
        #print("Current file:", path)
        # tqdm creates a handy progress bar for for loops. See
        # https://tqdm.github.io/
        # There are two try/except statements nested within another 
        # try/except statement below. This method allows the function
        # to only try to generate current_image once, thus saving time.
        try:
            # The following code is based on
            # https://github.com/ianare/exif-py .
            with open(path, 'rb') as file_handle:
                current_image = exifread.process_file(
                file_handle, extract_thumbnail=False,
                builtin_types=True, details=False)
                # Storing all of the keys from the current_image
                # dictionary as a set:
                available_metadata = set(current_image)
                # Here with editing
            if set({'GPS GPSLatitude', 'GPS GPSLatitudeRef',
                   'GPS GPSLongitude', 'GPS GPSLongitudeRef'}).issubset(
                available_metadata):      
                # Based on https://pypi.org/project/exif/

                lat_list = current_image['GPS GPSLatitude']
                lat_ref = current_image['GPS GPSLatitudeRef']
                # lat_list (which may actually be a list)
                # contains 3 numbers representing the 
                # degrees, minutes, and seconds that make up the
                # latitude coordinate, and lat_ref contains either
                # 'N' (for North) or 'S' (for South). lon_list
                # and lon_ref have similar formats. 

                lon_list = current_image['GPS GPSLongitude']
                lon_ref = current_image['GPS GPSLongitudeRef']

                # The following code converts these degree/minute/second
                # values into decimal degrees in order to make plotting
                # them easier.
                decimal_lat = lat_list[0] + lat_list[1]/60 + lat_list[2]/3600
                if lat_ref == 'S':
                    decimal_lat *= -1
                
                decimal_lon = lon_list[0] + lon_list[1]/60 + lon_list[2]/3600
                if lon_ref == 'W':
                    decimal_lon *= -1
                
                photo_location_lat = decimal_lat 
                photo_location_lon = decimal_lon

                df_pics.iloc[i, lat_column_position] = photo_location_lat
                df_pics.iloc[i, lon_column_position] = photo_location_lon

    
                # If no geotag data is found, the file will maintain its
                # default coordinates of 0, 0 that the mapping code will then
                # exclude.


            # The following try/except statement searches for a 'datetime'
            # value within the EXIF data. On certain devices on which
            # I tested this function, this datetime value had colons separating
            # the year, month, and date. Therefore, in order to get Pandas to 
            # convert it into a Pandas DateTime value, I first needed to
            # replace the first two colons in the datetime value
            # with hyphens (hence the replace() call below).

            # Determining the UTC time at which this image was
            # taken: (Note that both the original time and the offset
            # are necessary in order to calculate this value.)
            # Checking whether the values we need in order to 
            # produce this calculation are available within
            # our available metadata:
            if set({'EXIF DateTimeOriginal', 
                    'EXIF OffsetTimeOriginal'}).issubset(
                available_metadata):
                # Based on ChristopheD's response at
                # https://stackoverflow.com/a/2765967/13097194
                datetime_with_offset = (
                current_image['EXIF DateTimeOriginal'] 
                + current_image['EXIF OffsetTimeOriginal'])
                utc_metadata_creation_time = pd.to_datetime(
                datetime_with_offset, utc=True)
                df_pics.iloc[i, 
                utc_metadata_creation_time_position] = utc_metadata_creation_time
            elif set({'GPS GPSTimeStamp', 'GPS GPSDate'}).issubset(
                available_metadata):
            # Retrieving what I believe to be UTC time from
            # the GPS timestamp instead: (This is often available
            # when offset_time is not.)
            # (See https://exiftool.org/geotag.html)
                h, m, s, = current_image['GPS GPSTimeStamp']
                # These values showed up as 4.0, 13.0, and 34.0 in
                # the clip I checked--so some reformatting will
                # be necessary to convert them into timestamp-compatible
                # values.
                datetime_from_gps = (
                    current_image['GPS GPSDate'] + " " + ( 
                str(int(h)).zfill(2) + ":"+  str(int(m)).zfill(2) + ":"+
                str(int(s)).zfill(2)))
                utc_metadata_creation_time = pd.to_datetime(
                    datetime_from_gps, utc = True)
                # Note that passing utc=True will convert timestamps from
                # a localized time zone to UTC. For instance,
                # if the argument to pd.to_datetime() here is 
                # '2025-09-28 15:02:56-04:00',
                # the output will be Timestamp('2025-09-28 19:02:56+0000', tz='UTC') .
                # (Note that the time is advanced four hours and the -4
                # offset is replaced with +0.)
                df_pics.iloc[i, 
                utc_metadata_creation_time_position] = utc_metadata_creation_time
        except:
            pass

    df_pics['lat'] = pd.to_numeric(df_pics['lat'])
    df_pics['lon'] = pd.to_numeric(df_pics['lon'])
    # Replacing all beginning-of-epoch values with pd.NaT:
    df_pics['utc_metadata_creation_time'] = df_pics[
    'utc_metadata_creation_time'].replace(
    utc_epoch_start, pd.NaT)
    
    return df_pics


def retrieve_clip_locations(df_clips):
    ''' This function retrieves the geotag (geographic coordinate)
    data from a list of images. It assumes that the column names
    are the same as those created within generate_media_list.
    I have tested out this function with video files from both Samsung
    and Apple phones, but some tweaking may be needed in order to get it 
    to work on other devices.
    '''

    # Setting default values that will then get updated within the 
    # following code if valid data is found for them:
    # Clips' 'location' values, at least for the videos on my Samsung 
    # Galaxy S21 Ultra, consists of 17 characters that will then 
    # get split into a latitude and longitude component below.
    # Therefore, if no location data is present, the following
    # default value represents a set of 17 'x' characters that can still be
    # split into two parts.

    df_clips['raw_location'] = 'xxxxxxxxxxxxxxxxx'
    
    utc_epoch_start = pd.to_datetime(
    0, unit = 's', utc = True)
    
    
    df_clips['utc_metadata_creation_time'] = utc_epoch_start

    raw_loc_column_position = df_clips.columns.get_loc('raw_location')
    utc_metadata_creation_time_position = df_clips.columns.get_loc(
        'utc_metadata_creation_time')
    
    
    for i in tqdm(range(len(df_clips))):
        path = df_clips.iloc[i]['path']
        
        # There are two try/except statements nested within another 
        # try/except statement below. This method allows the function
        # to only try to generate the metadata object once, thus saving time.
        try:
            metadata = ffmpeg.probe(path)
            # Based on https://kkroening.github.io/ffmpeg-python/#ffmpeg.probe
            # The metadata dictionary for each video clip contains many
            # different components, so it's necessary to search through
            # the dictionary in order to retrieve the video location. 

            # I found iPhone video geotag data to be stored within
            # a 'com.apple.quicktime.location.ISO6709' key, whereas
            # Samsung video location data was stored within a 'location'
            # key, hence this if/else statement. Other devices may use
            # other keys.
            if 'location' in metadata['format']['tags'].keys():
                raw_location = metadata['format']['tags']['location']
                df_clips.iloc[i, 
                raw_loc_column_position] = raw_location
            elif 'com.apple.quicktime.location.ISO6709' in metadata[
            'format']['tags'].keys():
                raw_location = metadata['format']['tags'][
                    'com.apple.quicktime.location.ISO6709']
                df_clips.iloc[i, 
                raw_loc_column_position] = raw_location


            # I found that the st_mtime value (obtained via os.stat()
            # for at least one file wasn't actually accurate, whereas
            # the 'creation_time' value within the clip's
            # metadata was. Therefore, I'll also store
            # this tag (when it's available).

            if 'creation_time' in metadata[
                    'format']['tags'].keys():
                utc_metadata_creation_time = pd.to_datetime(metadata[
                'format']['tags']['creation_time'], utc = True)
                df_clips.iloc[i, 
                utc_metadata_creation_time_position] = utc_metadata_creation_time
            # Unlike st_mtime, which is 
            # expressed as an integer,
            # metadata_creation_time takes the form
            # of a UTC-formatted string (e.g.
            # '2025-04-30T23:04:45.000000Z' ).
            # This value wasn't available within
            # my older Sony camcorder files. 

            # The following statement searches for a 
            # 'com.apple.quicktime.creationdate' value within the video
            # metadata. I imagine this value will only be present within 
            # Apple devices. (A newer iPhone model that my wife has
            # did contain a 'creation_time' tag, so this item may only
            # be necessary for older phones.)
            
            elif 'com.apple.quicktime.creationdate' in metadata[
                'format']['tags'].keys():
                utc_metadata_creation_time = pd.to_datetime(metadata[
                    'format']['tags']['com.apple.quicktime.creationdate'],
                    utc=True) # The 'creationdate' tag that I checked
                # when writing this code showed a full time-zone-aware
                # datetime and not just the date--so it *should* be
                # equivalent to a regular 'creation_time' value, though
                # the offset may be local rather than UTC-based.
                df_clips.iloc[i, 
                utc_metadata_creation_time_position] = utc_metadata_creation_time
        except:
            pass
    
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

    df_clips['utc_metadata_creation_time'] = df_clips[
    'utc_metadata_creation_time'].replace(
    utc_epoch_start, pd.NaT)
    
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
timestamp_column = 'utc_metadata_creation_time', longitude_cutoff = 80, 
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

    folder_path: The path into which the map file should be saved.

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
    that each image/video was created. 

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

def create_map_screenshot(path_to_map_folder, map_name, 
screenshot_save_path = None, window_width = 3000):

    '''
    This function uses the Selenium library to create a screenshot 
    of a map so that it can be shared as a .png file.
    See https://www.selenium.dev/documentation/ for more information on 
    Selenium. 
    
    path_to_map_folder designates the path where
    the map is stored. (I wasn't able to get this code to work using
    just relative paths.) 

    map_name specifies the name of the map, including its extension.

    screenshot_save_path designates the folder where you wish to save
    the map screenshot. This can be a relative path.
    '''

    # Note: Some of the following code was based on similar code within
    # my Python for Nonprofits project at 
    # https://github.com/kburchfiel/pfn/blob/main/Mapping/folium_choropleth_map_functions.py .
    
    options = webdriver.ChromeOptions()
    options.add_argument(f'--window-size={window_width},{int(window_width*9/16)}')
    options.add_argument('--headless')
    # See https://www.selenium.dev/documentation/webdriver/getting_started/open_browser/
    # For more information on using Selenium to get screenshots of .html 
    # files, see my get_screenshots.ipynb file within my route_maps_builder
    # program, available here:
    # https://github.com/kburchfiel/route_maps_builder/blob/master/get_screenshots.ipynb
    driver = webdriver.Chrome(options=options) 
    driver.get(f'file://{path_to_map_folder}/{map_name}') 
    # See https://www.selenium.dev/documentation/webdriver/browser/navigation/
    time.sleep(3) # This gives the page sufficient
    # time to load the map tiles before the screenshot is taken. 
    # You can also experiment with longer sleep times.

    if screenshot_save_path != None:
        # If specifying a screenshot save path, you must create this path
        # within your directory before the function is run; otherwise,
        # it won't return an image. 
        driver.get_screenshot_as_file(
            screenshot_save_path+'/'+map_name.replace('.html','')+'.png') 
    else: # If no save path was specified for the screenshot, the image
        # will be saved within the project's root folder.
        driver.get_screenshot_as_file(
            map_name.replace('.html','')+'.png') 
    # Based on:
    # https://www.selenium.dev/selenium/docs/api/java/org/openqa/selenium/TakesScreenshot.html

    driver.quit()
    # Based on: https://www.selenium.dev/documentation/webdriver/browser/windows/

def batch_create_map_screenshots(path_to_map_folder, 
screenshot_save_path = None, window_width = 3840,
    intl_window_width = 4200):
    '''This function
    applies create_map_screenshot to all files within a folder. It assumes
    that the folder contains only image files.'''
    for root, dirs, files in os.walk(path_to_map_folder):
        maps_list = files
    for map in maps_list:
        # Setting separate widths for domestic and international maps:
        # (You may need to tweak these values depending on your own 
        # needs.)
        if '_intl' in map:
            window_width = intl_window_width
        create_map_screenshot(path_to_map_folder, 
        map_name = map, screenshot_save_path = screenshot_save_path,
        window_width = window_width)

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
    timestamp_column = 'utc_metadata_creation_time'):
    '''This function uses the geographic coordinate information within
    df_locations to estimate how far you've traveled each year. It assumes
    that the rows in df_locations are sorted in chronological order. 
    Otherwise, it will likely overestimate your travel distance by a large
    extent.'''
    df = df_locations.copy()
    df['distance'] = 0.0
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
    df['year'] = df[timestamp_column].dt.year
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