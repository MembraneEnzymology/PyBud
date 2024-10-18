import sys
import numpy as np
import tifffile as tiff
import csv
from pybud import PyBud
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QLabel, 
    QLineEdit, QPushButton, QScrollBar, QTableWidget, QAbstractItemView, QTableWidgetItem, QHeaderView, QFileDialog
)
from PyQt5.QtCore import Qt, QPointF, QPoint, QThread, pyqtSignal, QMimeData
from PyQt5.QtGui import QPixmap, QImage, QIcon, QPainter, QPen, QColor

# Worker thread for running fit_cells in the background
class FitCellsWorker(QThread):
    finished = pyqtSignal()

    def __init__(self, pybud, tif_data, pixel_size, brightfield_channel, fl_channels, cell_radius, edge_size, edge_rel_min):
        super().__init__()
        self.pybud = pybud
        self.tif_data = tif_data
        self.pixel_size = pixel_size
        self.brightfield_channel = brightfield_channel
        self.fl_channels = fl_channels
        self.cell_radius = cell_radius
        self.edge_size = edge_size
        self.edge_rel_min = edge_rel_min

    def run(self):
        self.pybud.fit_cells(self.tif_data, self.pixel_size, self.brightfield_channel, self.fl_channels,
                             self.cell_radius, self.edge_size, self.edge_rel_min)
        self.finished.emit()

# Custom QLabel to handle mouse clicks
class ClickableImageLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # Reference to PyBudGUI

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            # Get the click position relative to the QLabel
            click_position = event.pos()

            # Get the pixmap and its dimensions
            pixmap = self.parent.image_label.pixmap()

            if pixmap is not None:
                pixmap_width = pixmap.width()
                pixmap_height = pixmap.height()

                x = click_position.x()
                y = click_position.y()

                # Ensure the click is within the image boundaries
                if 0 <= x <= pixmap_width and 0 <= y <= pixmap_height:
                    # Now scale back to original image coordinates
                    original_width = self.parent.tif_data.shape[3]
                    original_height = self.parent.tif_data.shape[2]

                    image_x = int(x * (original_width / pixmap_width))
                    image_y = int(y * (original_height / pixmap_height))

                    # Add or remove selection at this position
                    self.parent.handle_selection(image_x, image_y)

class PyBudGUI(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("PyBud Measurement Tool")
        self.setGeometry(100, 100, 1024, 768)

        self.fitting_method = 'geometric'
        self.selection_radius = 10
        self.pybud = PyBud(fitting_method=self.fitting_method, selection_radius=self.selection_radius)        
        self.image_scale = 1.5
        
        # Main Splitter: Vertical Splitter
        main_splitter = QSplitter(Qt.Vertical)
        self.setCentralWidget(main_splitter)

        # Upper Splitter: Divides Left (Form Fields) and Right (Image Display)
        upper_splitter = QSplitter(Qt.Horizontal)
        main_splitter.addWidget(upper_splitter)

        # Left Panel for Form Fields
        top_left_panel = QWidget(self)
        top_left_layout = QFormLayout(top_left_panel)  # Changed to QFormLayout for proper addRow support

        # Add form fields
        self.file_path = QLineEdit()
        browse_button = QPushButton("Browse")
        browse_button.clicked.connect(self.browse_file)
        file_layout = QHBoxLayout()
        file_layout.addWidget(self.file_path)
        file_layout.addWidget(browse_button)
        file_container = QWidget()
        file_container.setLayout(file_layout)
        top_left_layout.addRow("Measurement File:", file_container)

        self.pixel_size_line = QLineEdit("0.0645")
        top_left_layout.addRow("Pixel Size (um/pixel):", self.pixel_size_line)

        self.cell_radius_line = QLineEdit("4")
        top_left_layout.addRow("Maximum Cell Radius (um):", self.cell_radius_line)

        self.cell_edge_size_line = QLineEdit("1")
        top_left_layout.addRow("Cell Edge Size (um):", self.cell_edge_size_line)

        self.brightfield_channel_line = QLineEdit("0")
        top_left_layout.addRow("Brightfield Channel:", self.brightfield_channel_line)

        self.fluorescent_channel1_line = QLineEdit("1")
        top_left_layout.addRow("Fluorescent Channel 1:", self.fluorescent_channel1_line)

        self.fluorescent_channel2_line = QLineEdit("-1")
        top_left_layout.addRow("Fluorescent Channel 2 (-1 if none):", self.fluorescent_channel2_line)

        self.edge_rel_min_line = QLineEdit("30")
        top_left_layout.addRow("Relative Minimum Edge Difference (%)", self.edge_rel_min_line)

        # Set the width of the left panel to 400 pixels
        #top_left_panel.setFixedWidth(400)
        #upper_splitter.setSizes([200, 400])

        # Add this panel to the top layout
        upper_splitter.addWidget(top_left_panel)
        
        # Right Panel for Image Display
        right_widget = QWidget()
        right_layout = QVBoxLayout()

        # Placeholder for Image
        self.image_label = ClickableImageLabel(self)
        #self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setAlignment(Qt.AlignLeft)
        right_layout.addWidget(self.image_label)

        # Horizontal ScrollBar to scroll through frames
        self.scrollbar = QScrollBar(Qt.Horizontal)
        self.scrollbar.setMinimum(0)
        self.scrollbar.valueChanged.connect(self.update_frame)
        right_layout.addWidget(self.scrollbar)

        # Measure Button
        self.measure_button = QPushButton("Measure")
        self.measure_button.clicked.connect(self.add_measurements)
        right_layout.addWidget(self.measure_button)

        # Add right panel to splitter
        right_widget.setLayout(right_layout)
        upper_splitter.addWidget(right_widget)

        # Set the initial size of the left and right panels
        # The first number is for the left panel (top_left_panel), the second is for the right panel (right_widget)
        upper_splitter.setSizes([450, 500])

        # Lower Panel: Spreadsheet and Buttons
        lower_widget = QWidget()
        lower_layout = QVBoxLayout()

        # Spreadsheet
        self.table = QTableWidget(10, 10)  # 10 rows, 4 columns
        self.table.setHorizontalHeaderLabels(["Cell", "Frame", "X", "Y", "Major", "Minor", "Angle", "Volume", "Fluorescence 1", "Fluorescence 2"])
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)  # Disable editing
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)  # Make columns stretch
        lower_layout.addWidget(self.table)

        # Buttons
        button_layout = QHBoxLayout()
        self.save_button = QPushButton("Save to File")
        self.save_button.clicked.connect(self.save_measurements)
        self.copy_button = QPushButton("Copy to Clipboard")
        self.copy_button.clicked.connect(self.copy_measurements)
        button_layout.addWidget(self.save_button)
        button_layout.addWidget(self.copy_button)
        lower_layout.addLayout(button_layout)

        # Add lower panel to the main layout
        lower_widget.setLayout(lower_layout)
        main_splitter.addWidget(lower_widget)

        # Initialize image data variables
        self.tif_data = None
        self.current_frame = 0

    def browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Measurement File", "", "TIF Files (*.tif);;All Files (*)")
        if file_name:
            self.file_path.setText(file_name)
            self.load_tif(file_name)

    def load_tif(self, file_name):
        # Load the TIF file using tifffile
        self.tif_data = tiff.imread(file_name)  # Shape: (frames, channels, height, width)
        brightfield_channel = int(self.brightfield_channel_line.text())

        # Set scrollbar maximum to the number of frames
        self.scrollbar.setMaximum(self.tif_data.shape[0] - 1)

        # Display the first frame
        self.update_frame(self.current_frame)

    def handle_selection(self, x, y):
        """Handle selection on the image at (x, y)."""

        if self.pybud.contains_selection(self.current_frame, x, y):
            self.pybud.remove_selection(self.current_frame, x, y)
        else:
            self.pybud.add_selection(self.current_frame, x, y)

        self.update_frame(self.current_frame)  # Redraw the frame
        
    def update_frame(self, frame_index):
        if self.tif_data is not None:
            self.current_frame = frame_index
            brightfield_channel = int(self.brightfield_channel_line.text())

            frame = self.tif_data[frame_index, brightfield_channel]

            if frame.dtype == np.uint8:
                height, width = frame.shape
                image = QImage(frame.data, width, height, frame.strides[0], QImage.Format_Grayscale8)
            elif frame.dtype == np.uint16:
                frame_8bit = (frame / 256).astype(np.uint8)
                height, width = frame_8bit.shape
                image = QImage(frame_8bit.data, width, height, frame_8bit.strides[0], QImage.Format_Grayscale8)
            else:
                self.image_label.setText("Unsupported image format")
                return

            # Convert to a pixmap for display
            pixmap = QPixmap.fromImage(image)
            pixmap = pixmap.scaled(int(pixmap.width() * self.image_scale), int(pixmap.height() * self.image_scale), Qt.KeepAspectRatio)

            # Draw green crosses for selections instead of red circles
            painter = QPainter(pixmap)
            pen = QPen(QColor(0, 255, 0), 2)  # Green color for the crosses
            painter.setPen(pen)

            if self.current_frame in self.pybud.selections:
                for x, y in self.pybud.selections[self.current_frame]:
                    x = int(x * self.image_scale)
                    y = int(y * self.image_scale)
                    painter.drawLine(x - 5, y - 5, x + 5, y + 5)
                    painter.drawLine(x - 5, y + 5, x + 5, y - 5)

            painter.end()

            # draw all fitted cells
            for cell in self.pybud.cells:
                if cell.frame == self.current_frame:
                    ellipse = cell.ellipse

                    x = ellipse.get_x_center() * self.image_scale
                    y = ellipse.get_y_center() * self.image_scale
                    major = ellipse.get_major() * self.image_scale
                    minor = ellipse.get_minor() * self.image_scale
                    angle = ellipse.get_angle()

                    self.draw_ellipse(pixmap, x, y, major, minor, angle)

            # Display the updated pixmap
            self.image_label.setPixmap(pixmap)

    def draw_ellipse(self, pixmap, x, y, major, minor, angle):
        with QPainter(pixmap) as painter:
            painter.setPen(QPen(QColor(255, 255, 0, 128), 2))
            painter.translate(x, y)
            painter.rotate(angle)
            painter.drawEllipse(QPointF(0, 0), major / 2, minor / 2)
            
    def add_measurements(self):
        try:
            # Get the pixel size (float)
            pixel_size = float(self.pixel_size_line.text())
        except ValueError:
            self.show_error_message("Pixel Size must be a valid number.")
            return

        try:
            # Get the maximum cell radius (integer)
            cell_radius = int(self.cell_radius_line.text())
        except ValueError:
            self.show_error_message("Maximum Cell Radius must be a valid integer.")
            return

        try:
            # Get the cell edge size (integer)
            edge_size = int(self.cell_edge_size_line.text())
        except ValueError:
            self.show_error_message("Cell Edge Size must be a valid integer.")
            return

        try:
            # Get the brightfield channel (integer)
            brightfield_channel = int(self.brightfield_channel_line.text())
        except ValueError:
            self.show_error_message("Brightfield Channel must be a valid integer.")
            return

        try:
            # Get the fluorescent channel 1 (integer)
            fluorescent_channel1 = int(self.fluorescent_channel1_line.text())
        except ValueError:
            self.show_error_message("Fluorescent Channel 1 must be a valid integer.")
            return

        if fluorescent_channel1 < 0:
            self.show_error_message("Fluorescent Channel 1 has to be set (cannot be -1).")
            return
        
        try:
            # Get the fluorescent channel 2 (integer)
            fluorescent_channel2 = int(self.fluorescent_channel2_line.text())
        except ValueError:
            self.show_error_message("Fluorescent Channel 2 must be a valid integer.")
            return

        try:
            # Get the relative minimum edge difference (float)
            edge_rel_min = float(self.edge_rel_min_line.text())
        except ValueError:
            self.show_error_message("Relative Minimum Edge Difference must be a valid number.")
            return

        fl_channels = [fluorescent_channel1]
        if fluorescent_channel2 >= 0:
            fl_channels.append(fluorescent_channel2)

       # Create a worker to run the fit_cells function in a background thread
        self.worker = FitCellsWorker(self.pybud, self.tif_data, pixel_size, brightfield_channel,
                                     fl_channels, cell_radius, edge_size, edge_rel_min)

        # Show "Tracking Cells..." message
        self.statusBar().showMessage("Tracking Cells...")

        # Connect the worker's finished signal to a slot that updates the table
        self.worker.finished.connect(self.on_fit_cells_finished)

        # Start the worker
        self.worker.start()

        
    def on_fit_cells_finished(self):
        """Called when fit_cells completes."""
        self.statusBar().clearMessage()
        self.populate_table()


    def populate_table(self):
        # Set the table to have as many rows as there are fitted cells
        self.table.setRowCount(len(self.pybud.cells))

        for row, cell in enumerate(self.pybud.cells):
            fl1 = cell.fluorescence[0].mean
            fl2 = cell.fluorescence[1].mean if len(cell.fl_channels) > 1 else 0

            self.table.setItem(row, 0, QTableWidgetItem(str(cell.id)))
            self.table.setItem(row, 1, QTableWidgetItem(str(cell.frame)))
            self.table.setItem(row, 2, QTableWidgetItem(f"{cell.x_centroid:.2f}"))
            self.table.setItem(row, 3, QTableWidgetItem(f"{cell.y_centroid:.2f}"))
            self.table.setItem(row, 4, QTableWidgetItem(f"{cell.major:.2f}"))
            self.table.setItem(row, 5, QTableWidgetItem(f"{cell.minor:.2f}"))
            self.table.setItem(row, 6, QTableWidgetItem(f"{cell.angle:.2f}"))
            self.table.setItem(row, 7, QTableWidgetItem(f"{cell.volume:.2f}"))
            self.table.setItem(row, 8, QTableWidgetItem(f"{fl1:.2f}"))
            self.table.setItem(row, 9, QTableWidgetItem(f"{fl2:.2f}"))

        self.update_frame(self.current_frame)

    def save_measurements(self):
        # Open a file dialog to select where to save the CSV
        options = QFileDialog.Options()
        file_name, _ = QFileDialog.getSaveFileName(self, "Save CSV File", "", "CSV Files (*.csv);;All Files (*)", options=options)
        
        if file_name:
            # Ensure the file has the right extension
            if not file_name.endswith('.csv'):
                file_name += '.csv'

            # Open the file and write the table content to it
            with open(file_name, mode='w', newline='') as file:
                writer = csv.writer(file)
                # Write headers
                headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
                writer.writerow(headers)
                
                # Write rows
                for row in range(self.table.rowCount()):
                    row_data = []
                    for column in range(self.table.columnCount()):
                        item = self.table.item(row, column)
                        row_data.append(item.text() if item else '')
                    writer.writerow(row_data)
                    
            print(f"Data saved to {file_name}")

    def copy_measurements(self):
        # Prepare the clipboard data
        clipboard = QApplication.clipboard()
        mime_data = QMimeData()

        # Gather table content
        table_data = ""
        headers = [self.table.horizontalHeaderItem(i).text() for i in range(self.table.columnCount())]
        table_data += "\t".join(headers) + "\n"
        
        for row in range(self.table.rowCount()):
            row_data = []
            for column in range(self.table.columnCount()):
                item = self.table.item(row, column)
                row_data.append(item.text() if item else '')
            table_data += "\t".join(row_data) + "\n"

        # Set the clipboard text
        mime_data.setText(table_data)
        clipboard.setMimeData(mime_data)
        
        print("Data copied to clipboard")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setWindowIcon(QIcon("images/icon.png"))

    window = PyBudGUI()
    window.show()
    sys.exit(app.exec_())
