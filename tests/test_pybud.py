from pybud import PyBud
import tifffile as tiff

pb = PyBud()

file_name = r"tests/BudJstack.tif"
pixel_size = 0.0645  # microns per pixel
bf_channel = 0
fl_channels = [1]
cell_radius = 4 # micrometer
edge_size = 1 # micrometer
edge_rel_min = 30 # 30% of the background

img = tiff.imread(file_name)

pb.add_selection(0, 90, 94)
pb.add_selection(0, 119, 153)
pb.add_selection(0, 177, 97)
pb.add_selection(29, 124, 96)
pb.fit_cells(img, pixel_size, bf_channel, fl_channels, cell_radius, edge_size, edge_rel_min)