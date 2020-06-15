import glob
import numpy as np
import os
import rasterio
import stat
import weakref

from yt.data_objects.static_output import \
    Dataset
from yt.frontends.ytdata.data_structures import \
    YTGridHierarchy

from .fields import \
    GeoTiffFieldInfo
from .utilities import \
    left_aligned_coord_cal, \
    save_dataset_as_geotiff, \
    parse_awslandsat_metafile \

class GeoTiffHierarchy(YTGridHierarchy):
    def _detect_output_fields(self):
        self.field_list = []
        self.ds.field_units = self.ds.field_units or {}
        with rasterio.open(self.ds.parameter_filename, "r") as f:
            group = 'bands'
            for _i in range(1, f.count + 1):
                field_name = (group, str(_i))
                self.field_list.append(field_name)
                self.ds.field_units[field_name] = ""

    def _count_grids(self):
        self.num_grids = 1

class GeoTiffDataset(Dataset):
    """Dataset for saved covering grids, arbitrary grids, and FRBs."""
    _index_class = GeoTiffHierarchy
    _field_info_class = GeoTiffFieldInfo
    _dataset_type = 'geotiff'
    geometry = "cartesian"
    default_fluid_type = "bands"
    fluid_types = ("bands", "index")
    periodicity = np.zeros(3, dtype=bool)

    _con_attrs = ()

    def __init__(self, filename):
        super(GeoTiffDataset, self).__init__(filename,
                                        self._dataset_type)
        self.data = self.index.grids[0]

    def _parse_parameter_file(self):
        self.num_particles = {}

        with rasterio.open(self.parameter_filename, "r") as f:
            for key in f.meta.keys():
                v = f.meta[key]
                self.parameters[key] = v
            # self.parameters['transform'] = f.transform

        ### TODO: can we get time info from metadata?
        self.current_time = 0.
        self.unique_identifier = \
            int(os.stat(self.parameter_filename)[stat.ST_CTIME])

        self.cosmological_simulation = False
        self.domain_dimensions = np.array([self.parameters['height'],
                                           self.parameters['width'],
                                           1], dtype=np.int32)
        self.dimensionality = 3
        rightedge_xy = left_aligned_coord_cal(self.domain_dimensions[0],
                                          self.domain_dimensions[1],
                                          self.parameters['transform'])

        self.domain_left_edge = self.arr(np.zeros(self.dimensionality,
                                                   dtype=np.float64), 'm')
        self.domain_right_edge = self.arr([rightedge_xy[0],
                                          rightedge_xy[1],
                                          1], 'm', dtype=np.float64)

    def _set_code_unit_attributes(self):
        attrs = ('length_unit', 'mass_unit', 'time_unit',
                 'velocity_unit', 'magnetic_unit')
        si_units = ('m', 'g', 's', 'm/s', 'gauss')
        base_units = np.ones(len(attrs), dtype=np.float64)
        for unit, attr, si_unit in zip(base_units, attrs, si_units):
            setattr(self, attr, self.quan(unit, si_unit))

    def _setup_gas_alias(self):
        "Alias the grid type to gas with a field alias."

        for ftype, field in self.field_list:
            if ftype == "grid":
                self.field_info.alias(("gas", field), ("grid", field))

    def save_as(self, filename):
        ### TODO: generalize this to save any dataset type as GeoTiff.
        return save_dataset_as_geotiff(self, filename)

    @classmethod
    def _is_valid(self, *args, **kwargs):
        if not (args[0].endswith(".tif") or \
            args[0].endswith(".tiff")): return False
        with rasterio.open(args[0], "r") as f:
            driver_type = f.meta["driver"]
            if driver_type == "GTiff":
                return True
        return False

class LandSatGeoTiffHierarchy(GeoTiffHierarchy):
    def _detect_output_fields(self):
        self.field_list = []
        self.ds.field_units = self.ds.field_units or {}

        # get list of filekeys
        filekeys = [s for s in self.ds.parameters.keys() if 'FILE_NAME_BAND_' in s]
        files = [self.ds.data_dir + self.ds.parameters[filekey] for filekey in filekeys]

        group = 'bands'
        for file in files:
            band = file.split(os.path.sep)[-1].split('.')[0].split('B')[1]
            field_name = (group, band)
            self.field_list.append(field_name)
            self.ds.field_units[field_name] = ""

class LandSatGeoTiffDataSet(GeoTiffDataset):
    """"""
    _index_class = LandSatGeoTiffHierarchy

    def _parse_parameter_file(self):
        self.current_time = 0.
        self.unique_identifier = \
            int(os.stat(self.parameter_filename)[stat.ST_CTIME])

        self.cosmological_simulation = False

        # self.parameter_filename is the dir str
        if self.parameter_filename[-1] == '/':
            self.data_dir = self.parameter_filename
            self.mtlfile = self.data_dir + self.parameter_filename[:-1].split(os.path.sep)[-1] + '_MTL.txt'
            self.angfile = self.data_dir + self.parameter_filename[:-1].split(os.path.sep)[-1] + '_ANG.txt'
        else:
            self.data_dir = self.parameter_filename + '/'
            self.mtlfile = self.data_dir + self.parameter_filename.split(os.path.sep)[-1] + '_MTL.txt'
            self.angfile = self.data_dir + self.parameter_filename .split(os.path.sep)[-1]+ '_ANG.txt'
        # load metadata files
        self.parameters.update(parse_awslandsat_metafile(self.angfile))
        self.parameters.update(parse_awslandsat_metafile(self.mtlfile))

        # get list of filekeys
        filekeys = [s for s in self.parameters.keys() if 'FILE_NAME_BAND_' in s]
        files = [self.data_dir + self.parameters[filekey] for filekey in filekeys]
        self.parameters['count'] = len(filekeys)
        # take the parameters displayed in the filename
        self._parse_landsat_filename_data(self.parameter_filename.split(os.path.sep)[-1])

        for filename in files:
            band = filename.split(os.path.sep)[-1].split('.')[0].split('B')[1]
            # filename = self.parameters[band]
            with rasterio.open(filename, "r") as f:
                for key in f.meta.keys():
                    # skip key if already defined as a parameter
                    if key in self.parameters.keys(): continue
                    v = f.meta[key]
                    # if key == "con_args":
                    #     v = v.astype("str")
                    self.parameters[(band, key)] = v
                self._with_parameter_file_open(f)
                # self.parameters['transform'] = f.transform

            if band == '1':
                self.domain_dimensions = np.array([self.parameters[(band, 'height')],
                                                   self.parameters[(band, 'width')],
                                                   1], dtype=np.int32)
                self.dimensionality = 3
                rightedge_xy = left_aligned_coord_cal(self.domain_dimensions[0],
                                                  self.domain_dimensions[1],
                                                  self.parameters[(band, 'transform')])

                self.domain_left_edge = self.arr(np.zeros(self.dimensionality,
                                                           dtype=np.float64), 'm')
                self.domain_right_edge = self.arr([rightedge_xy[0],
                                                  rightedge_xy[1],
                                                  1], 'm', dtype=np.float64)

    def _parse_landsat_filename_data(self, filename):
        """
        "LXSS_LLLL_PPPRRR_YYYYMMDD_yyyymmdd_CC_TX"
        L = Landsat
        X = Sensor ("C"=OLI/TIRS combined,
                    "O"=OLI-only, "T"=TIRS-only, 
                    E"=ETM+, "T"="TM, "M"=MSS)
        SS = Satellite ("07"=Landsat 7, "08"=Landsat 8)
        LLLL = Processing correction level (L1TP/L1GT/L1GS)
        PPP = WRS path
        RRR = WRS row
        YYYYMMDD = Acquisition year, month, day
        yyyymmdd - Processing year, month, day
        CC = Collection number (01, 02, …)
        TX = Collection category ("RT"=Real-Time, "T1"=Tier 1,
                                  "T2"=Tier 2)
        """
        sensor = {"C": "OLI&TIRS combined",
                  "O": "OLI-only",
                  # "T": "TIRS-only", commenting out to fix flake8 error
                  "E": "ETM+", "T": "TM", "M": "MSS"}
        satellite = {"07": "Landsat 7",
                     "08": "Landsat 8"}
        category = {"RT": "Real-Time", "T1": "Tier 1",
                    "T2": "Tier 2"}

        self.parameters['sensor'] = sensor[filename[1]]
        self.parameters['satellite'] = satellite[filename[2:4]]
        self.parameters['level'] = filename[5:9]

        self.parameters['wrs'] = {'path': filename[10:13],
                                  'row': filename[13:16]}

        self.parameters['acquisition_time'] = {'year': filename[17:21],
                                               'month': filename[21:23],
                                               'day': filename[23:25]}
        self.parameters['processing_time'] = {'year': filename[26:30],
                                              'month': filename[30:32],
                                              'day': filename[32:34]}
        self.parameters['collection'] = {
                                'number': filename[35:37],
                                'category': category[filename[38:40]]}

    @classmethod
    def _is_valid(self, *args, **kwargs):
        if not os.path.isdir(args[0]): return False
        if len(glob.glob(args[0]+'/L*_ANG.txt')) != 1 and\
           len(glob.glob(args[0]+'/L*_MTL.txt')) != 1: return False
        try:
            file = glob.glob(args[0]+'/*.TIF')[0] # open the first file
            with rasterio.open(file, "r") as f:
                # data_type = parse_gtif_attr(f, "dtype")
                driver_type = f.meta["driver"]
                # if data_type == "uint16":
                #     return True
                if driver_type == "GTiff":
                    return True
        except:
            pass
        return False
