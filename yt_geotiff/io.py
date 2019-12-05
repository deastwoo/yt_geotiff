"""
yt_geotiff data-file handling function.



"""
import numpy as np

import rasterio


from yt.utilities.io_handler import \
    BaseIOHandler


class IOHandlerYTGTiff(BaseIOHandler):
    _dataset_type = "ytgeotiff"
    _base = slice(None)
    _field_dtype = "float64"

    def __init__(self, ds, *args, **kwargs):
        super(IOHandlerYTGTiff, self).__init__(ds)

    def _read_fluid_selection(self, chunks, selector, fields, size):
        chunks = list(chunks)
        # if any(( not (ftype == "boxlib" or ftype == 'raw') for ftype, fname in fields)):
        #     raise NotImplementedError
        rv = {}
        raw_fields = []
        for field in fields:
            if field[0] == "raw":
                nodal_flag = self.ds.nodal_flags[field[1]]
                num_nodes = 2**sum(nodal_flag)
                rv[field] = np.empty((size, num_nodes), dtype="float64")
                raw_fields.append(field)
            else:
                rv[field] = np.empty(size, dtype="float64")
        centered_fields = _remove_raw(fields, raw_fields)
        ng = sum(len(c.objs) for c in chunks)
        mylog.debug("Reading %s cells of %s fields in %s grids",
                    size, [f2 for f1, f2 in fields], ng)
        ind = 0
        for chunk in chunks:
            data = self._read_chunk_data(chunk, centered_fields)
            for g in chunk.objs:
                for field in fields:
                    if field in centered_fields:
                        ds = data[g.id].pop(field)
                    else:
                        ds = self._read_raw_field(g, field)
                    nd = g.select(selector, ds, rv[field], ind)
                ind += nd
                data.pop(g.id)
        return rv

    def _read_raw_field(self, grid, field):
        band = field[1] # band number
        with rasterio.open(self.ds.parameter_filename, "r") as f:
            field_data = f.read(int(band))
        return field_data

    def _read_chunk_data(self, chunk, fields):
        data = {}
        grids_by_file = defaultdict(list)
        if len(chunk.objs) == 0: return data
        for g in chunk.objs:
            if g.filename is None:
                continue
            grids_by_file[g.filename].append(g)
        dtype = self.ds.index._dtype
        bpr = dtype.itemsize
        for filename in grids_by_file:
            grids = grids_by_file[filename]
            grids.sort(key = lambda a: a._offset)
            f = rasterio.open(filename, "r")
            for grid in grids:
                data[grid.id] = {}
                local_offset = grid._get_offset(f) - f.tell()
                count = grid.ActiveDimensions.prod()
                size = count * bpr
                for field in self.ds.index.field_order:
                    if field in fields:
                        # We read it ...
                        f.seek(local_offset, os.SEEK_CUR)
                        v = np.fromfile(f, dtype=dtype, count=count)
                        v = v.reshape(grid.ActiveDimensions, order='F')
                        data[grid.id][field] = v
                        local_offset = 0
                    else:
                        local_offset += size
        return data