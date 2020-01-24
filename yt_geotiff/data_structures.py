"""
Data structures for yt_geotiff.



"""


import os
import weakref
import numpy as np
import rasterio


from yt.data_objects.static_output import \
    Dataset
from yt.frontends.ytdata.data_structures import \
    YTGridHierarchy, YTGrid
# from yt.data_objects.grid_patch import \
#     AMRGridPatch

from yt import YTArray

from .fields import \
    YTGTiffFieldInfo
from .utilities import \
    coord_cal, left_aligned_coord_cal


class YTGTiffGrid(YTGrid):
    _id_offset = 0
    # __slots__ = ["_level_id"]
    def __init__(self, id, index, level=-1):
        YTGrid.__init__(self, id, filename=index.index_filename,
                              index=index)
        # self.Parent = None
        # self.Children = []
        # self.Level = level

class YTGTiffHierarchy(YTGridHierarchy):

    grid = YTGrid
    _data_file = None 

    def __init__(self, ds, dataset_type = None):
        self.dataset = weakref.proxy(ds)
        self.index_filename = os.path.abspath(
            self.dataset.parameter_filename)
        super(YTGTiffHierarchy, self).__init__(ds, dataset_type)

    def _detect_output_fields(self):
        self.field_list = []
        self.ds.field_units = self.ds.field_units or {}
        with rasterio.open(self.ds.parameter_filename, "r") as f:
            group = 'bands'
            for _i in range(1, f.count + 1):
                # group = f.read(_i)
                field_name = (str(group), str(_i))
                self.field_list.append(field_name)
                self.ds.field_units[field_name] = ""

    def _count_grids(self):
        self.num_grids = 1

    def _parse_index(self):
        """
        this must fill in grid_left_edge, grid_right_edge, grid_particle_count,
        grid_dimensions and grid_levels with the appropriate information. Each
        of these variables is an array, with an entry for each of the
        self.num_grids grids. Additionally, grids must be an array of
        AMRGridPatch objects that already know their IDs.
        """
        self.grid_dimensions[:] = self.ds.domain_dimensions
        self.grid_left_edge[:] = self.ds.domain_left_edge
        self.grid_right_edge[:] = self.ds.domain_right_edge
        self.grid_levels[:] = np.zeros(self.num_grids)
        self.grid_procs = np.zeros(self.num_grids)
        self.grid_particle_count[:] = sum(self.ds.num_particles.values())
        self.grids = []
        for gid in range(self.num_grids):
            self.grids.append(self.grid(gid, self))
            self.grids[gid].Level = self.grid_levels[gid, 0]
        self.max_level = self.grid_levels.max()
        temp_grids = np.empty(self.num_grids, dtype='object')
        for i, grid in enumerate(self.grids):
            grid.filename = self.ds.parameter_filename
            grid._prepare_grid()
            grid.proc_num = self.grid_procs[i]
            temp_grids[i] = grid
        self.grids = temp_grids

    def _populate_grid_objects(self):
        """
        this initializes the grids by calling _prepare_grid() and _setup_dx()
        on all of them. Additionally, it should set up Children and Parent
        lists on each grid object.
        """
        for g in self.grids:
            g._setup_dx()
            # # this is non-spatial, so remove the code_length units
            # g.dds = self.ds.arr(g.dds.d, "")
            # g.ActiveDimensions = self.ds.domain_dimensions
        self.max_level = self.grid_levels.max()




class YTGTiffDataset(Dataset):
    """Dataset for saved covering grids, arbitrary grids, and FRBs."""
    _index_class = YTGTiffHierarchy
    _field_info_class = YTGTiffFieldInfo
    _dataset_type = 'ytgeotiff'
    geometry = "cartesian"
    default_fluid_type = "bands"
    # fluid_types = ("grid", "gas", "deposit", "index")
    fluid_types = ("bands", "index") #"grid", "index")
    periodicity = np.zeros(3, dtype=bool)
    units_override = {'length': 'm', # geotiff projection units
                      'time': 's'}

    _con_attrs = ()

    def __init__(self, filename):
        print 
        super(YTGTiffDataset, self).__init__(filename,
                                             self._dataset_type,
                                             units_override=self.units_override)
        self.data = self.index.grids[0]

    # def set_units(self):
    #     """
    #     Overide the set_units function of Dataset: we don't have units in our
    #     GeoTiff. This will need a metadatafile
    #     """
    #     # print "set_units overide"
    #     self.set_code_units()

    def _parse_parameter_file(self):
        # self.refine_by = 2
        with rasterio.open(self.parameter_filename, "r") as f:
            for key in f.meta.keys():
                v = f.meta[key]
                # if key == "con_args":
                #     v = v.astype("str")
                self.parameters[key] = v
            self._with_parameter_file_open(f)
            self.parameters['transform'] = f.transform

        # # No time steps/snapshots
        self.current_time = 0.
        self.unique_identifier = 0
        self.parameters["cosmological_simulation"] = False
        self.domain_dimensions = np.array([self.parameters['height'],
                                           self.parameters['width'],
                                           1], dtype=np.int32)
        self.dimensionality = 3
        rightedge_xy = left_aligned_coord_cal(self.domain_dimensions[0],
                                          self.domain_dimensions[1],
                                          self.parameters['transform'])
        # self.domain_left_edge = np.zeros(self.dimensionality,
        #                                            dtype=np.float64)
        # self.domain_right_edge = np.array([rightedge_xy[0],
        #                                   rightedge_xy[1],
        #                                   1], dtype=np.float64)

        self.domain_left_edge = self.arr(np.zeros(self.dimensionality,
                                                   dtype=np.float64), 'm')
        self.domain_right_edge = self.arr([rightedge_xy[0],
                                          rightedge_xy[1],
                                          1], 'm', dtype=np.float64)

        # Overide the code units as no units are provided
        self._override_code_units()

    def _set_code_unit_attributes(self):
        attrs = ('length_unit', 'mass_unit', 'time_unit',
                 'velocity_unit', 'magnetic_unit')
        si_units = ('m', 'g', 's', 'm/s', 'gauss')
        base_units = np.ones(len(attrs), dtype=np.float64)
        for unit, attr, si_unit in zip(base_units, attrs, si_units):
            setattr(self, attr, self.quan(unit, si_unit))

    # def _override_code_units(self):
    #     pass
        # setattr(self, 'length_unit', self.quan(1.0, 'm'))
        # setattr(self, 'time_unit', self.quan(1.0, 's'))
        # setattr(self, 'code_length', self.quan(1.0, 'm'))
        # setattr(self, 'code_time', self.quan(1.0, 's'))

    def create_field_info(self):
        self.field_dependencies = {}
        self.derived_field_list = []
        self.filtered_particle_types = []
        self.field_info = self._field_info_class(self, self.field_list)
        self.coordinates.setup_fields(self.field_info)
        self.field_info.setup_fluid_fields()
        for ptype in self.particle_types:
            self.field_info.setup_particle_fields(ptype)

        self._setup_gas_alias()
        self.field_info.setup_fluid_index_fields()
        self.field_info.setup_extra_union_fields()
        # mylog.debug("Loading field plugins.")
        self.field_info.load_all_plugins()
        deps, unloaded = self.field_info.check_derived_fields()
        self.field_dependencies.update(deps)

    def _setup_override_fields(self):
        pass

    def _with_parameter_file_open(self, f):
        self.num_particles = \
          dict([('n', 0)])

    def _setup_gas_alias(self):
        "Alias the grid type to gas with a field alias."

        for ftype, field in self.field_list:
            if ftype == "grid":
                self.field_info.alias(("gas", field), ("grid", field))

    @classmethod
    def _is_valid(self, *args, **kwargs):
        if not (args[0].endswith(".tif") or args[0].endswith(".tiff")): return False
        with rasterio.open(args[0], "r") as f:
            # data_type = parse_gtif_attr(f, "dtype")
            driver_type = f.meta["driver"]
            # if data_type == "uint16":
            #     return True
            if driver_type == "GTiff":
                return True
        return False

