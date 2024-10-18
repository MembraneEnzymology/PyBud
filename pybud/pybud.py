import numpy as np
import numpy.typing as npt
from typing import List
from .cell import Cell

class PyBud:

    def __init__(self, fitting_method='algebraic', selection_radius=10):
        self.selection_radius = selection_radius
        
        self.cells: List[Cell] = []
        self.selections = {}

    def contains_selection(self, frame, x, y):
        if frame in self.selections:
            for i, (sx, sy) in enumerate(self.selections[frame]):
                if np.hypot(sx - x, sy - y) <= self.selection_radius:  # Check distance
                    return True
        return False

    def add_selection(self, frame, x, y):
        if frame not in self.selections:
            self.selections[frame] = []
        self.selections[frame].append((x, y))

    def remove_selection(self, frame, x, y):
        if frame in self.selections:
            for i, (sx, sy) in enumerate(self.selections[frame]):
                if np.hypot(sx - x, sy - y) <= self.selection_radius:  # Check distance
                    del self.selections[frame][i]
                    return True
        return False

    def clear(self):
        self.selections.clear()
        self.cells.clear()
        
    def fit_cells(self, img, pixel_size: float, bf_channel: int, fl_channels: List, cell_radius, edge_size, edge_rel_min):
        self.cells = []

        cell_id = 1
        for start_frame, coordinates in self.selections.items():
            for x, y in coordinates:
                for frame in range(start_frame, img.shape[0]):

                    cell = Cell(img, pixel_size, bf_channel, fl_channels, frame, x, y, cell_id, int(np.ceil(cell_radius / pixel_size)), int(np.ceil(edge_size / pixel_size)), edge_rel_min)

                    if cell.cell_found:
                        self.cells.append(cell)
                        x = cell.ellipse.get_x_center()
                        y = cell.ellipse.get_y_center()
                        print(f"cell found on channel {bf_channel} at frame {frame} x {x} y {y}")
                    else:
                        break
                cell_id += 1

