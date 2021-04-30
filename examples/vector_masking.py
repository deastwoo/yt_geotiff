"""
Example script for selecting subset of image using binary mask with rasterio.

author: dan.eastwood@astrosat.net
"""

import numpy as np
import rasterio
from rasterio.mask import mask
import fiona
from shapely.geometry import Polygon


def apply_mask(raster_path, out_path, shapes):
    """Apply mask and output new raster file.
    Input
    -----
    raster_path (string)        Path to input raster
    shapes (iterable object)    The values must be a GeoJSON-like dict or an
                                object that implements the Python geo interface
                                protocol (such as a Shapely Polygon).

    """
    print("\nOriginal raster stats:")

    with rasterio.open(raster_path) as src:
        data = src.read(1)
        nodata = src.nodata

    print("array shape:", data.shape)
    print("mean value:", np.nanmean(data[data != nodata]))

    with rasterio.open(raster_path) as src:
        out_image, out_transform = mask(
            src,
            shapes,
            crop=True  # this option crops the image to the bounds of the shape
        )
        out_meta = src.meta

    print("\nMasked raster stats:")
    print("array shape:", out_image.shape)
    print("mean:", np.nanmean(out_image[out_image != nodata]))

    print("\nold meta data:")
    print(out_meta)

    out_meta.update(
        {
            "driver": "GTiff",
            "height": out_image.shape[1],
            "width": out_image.shape[2],
            "transform": out_transform
        }
    )

    print("\nnew meta data:")
    print(out_meta)

    with rasterio.open(out_path, "w", **out_meta) as dest:
        dest.write(out_image)


def play_with_shapely(shape):
    """A few things we can do with shapely. Not key to this example."""
    wkt = shape.wkt
    coords = list(shape.exterior.coords)
    area = shape.area
    bounds = shape.bounds
    envelope = shape.envelope.wkt  # converted into WKT representation
    print(f"The WKT format for the polygon:\n {wkt}\n")
    print(f"The raw polygon coordinates:\n {coords}\n")
    print(f"The polygon area:\n {area}\n")
    print(f"The polygon bounds (minx, miny, maxx, maxy):\n {bounds} \n")
    print(f"A rectangle encompassing the polygon:\n {envelope}")


def main():
    """
    Open shapefile and apply geometry as a mask to raster.

    The first step is to use fiona to read the shapefile. At read time fiona
    returns the following GeoJSON-like dict format:
    [
        {
            'type': 'Feature',
            'id': <id string>,
            'properties': OrderedDict(...),
            'geometry': {
                'type': 'Polygon',
                'coordinates': [
                    [
                        (
                            <x_coord>,
                            <y_coord>
                        ), ...
                    ]
                ]
            }
        }
    ]

    Selecting the "geometry" from the dictionary of each feature you get a dict
    which can then be fed into rasterio's mask function.
    """
    raster_path = (
        "/path/to/Landsat-8_sample_L2/"
        "LC08_L2SP_171060_20210227_20210304_02_T1_ST_B10.TIF"
    )
    shpfile_path = (
        "/path/to/polygon/"
        "polygon.shp"
    )  # already converted to the same CRS as the raster!

    # read shapefile with fiona
    with fiona.open(shpfile_path, "r") as shapefile:
        shapes_from_file = [feature["geometry"] for feature in shapefile]

    print(f"Number of features in file: {len(shapes_from_file)}")

    # define a polygon with shapely using the list of coordinates
    shape = Polygon(shapes_from_file[0]["coordinates"][0])
    # with shapely polygon object we can do a few things...
    play_with_shapely(shape)

    # apply vector as a raster mask
    out_path = '.'.join(raster_path.split('.')[:-1]) + "_masked.TIF"
    apply_mask(raster_path, out_path, shapes_from_file)

    # a repeat of the above but with the shapely polygon
    out_path = '.'.join(raster_path.split('.')[:-1]) + "_masked_shapely.TIF"
    apply_mask(raster_path, out_path, [shape])


if __name__ == '__main__':
    main()
