import pybud
import tifffile as tiff

def test_cell_tracking():
    # Load the image stack
    stack_path = 'tests/BudJstack.tif'
    img = tiff.imread(stack_path)
    cell = pybud.Cell(img, 0, 0, 118, 151)
    cell.get_cell_edge()
    print(cell.found_x, cell.found_y)
    


if __name__ == "__main__":
    test_cell_tracking()
