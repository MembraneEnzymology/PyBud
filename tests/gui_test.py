import sys
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QSplitter, QVBoxLayout, QHBoxLayout, QFormLayout, QWidget, QLabel, 
    QLineEdit, QPushButton, QScrollBar, QTableWidget, QAbstractItemView, QTableWidgetItem, QHeaderView, QTableWidget, QFileDialog
)
from PyQt5.QtCore import Qt, QPointF
from PyQt5.QtGui import QPixmap, QImage
import numpy as np
import tifffile as tiff
from PyQt5.QtCore import QPoint
from PyQt5.QtGui import QPainter, QPen, QColor

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

        self.pixel_size = QLineEdit("0.1")
        top_left_layout.addRow("Pixel Size (um/pixel):", self.pixel_size)

        self.max_radius = QLineEdit("50")
        top_left_layout.addRow("Maximum Cell Radius (um):", self.max_radius)

        self.cell_edge_size = QLineEdit("5")
        top_left_layout.addRow("Cell Edge Size (um):", self.cell_edge_size)

        self.brightfield_channel = QLineEdit("0")
        top_left_layout.addRow("Brightfield Channel:", self.brightfield_channel)

        self.fluorescent_channel1 = QLineEdit("1")
        top_left_layout.addRow("Fluorescent Channel 1:", self.fluorescent_channel1)

        self.fluorescent_channel2 = QLineEdit("-1")
        top_left_layout.addRow("Fluorescent Channel 2:", self.fluorescent_channel2)

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

        self.selections = {}  # Dictionary to store selections for each frame
        self.radius = 10  # Circle radius (in pixels)

        self.fitted_cells = {}

        # remove this line in final version!
        self.load_tif(r"X:\My Documents\msb\code\PyBud\tests\BudJstack.tif")

    def browse_file(self):
        file_name, _ = QFileDialog.getOpenFileName(self, "Select Measurement File", "", "TIF Files (*.tif);;All Files (*)")
        if file_name:
            self.file_path.setText(file_name)
            self.load_tif(file_name)

    def load_tif(self, file_name):
        # Load the TIF file using tifffile
        self.tif_data = tiff.imread(file_name)  # Shape: (frames, channels, height, width)
        brightfield_channel = int(self.brightfield_channel.text())

        # Set scrollbar maximum to the number of frames
        self.scrollbar.setMaximum(self.tif_data.shape[0] - 1)

        # Display the first frame
        self.update_frame(self.current_frame)

    def handle_selection(self, x, y):
        """Handle selection on the image at (x, y)."""
        if self.current_frame not in self.selections:
            self.selections[self.current_frame] = []

        frame_selections = self.selections[self.current_frame]

        # Check if the clicked position is near an existing selection
        for i, (sx, sy) in enumerate(frame_selections):
            if np.hypot(sx - x, sy - y) <= self.radius:  # Check distance
                # Remove selection if clicked again
                del frame_selections[i]
                self.update_frame(self.current_frame)  # Redraw the frame
                return

        # Otherwise, add the new selection
        frame_selections.append((x, y))
        self.update_frame(self.current_frame)  # Redraw the frame
        
    def update_frame(self, frame_index):
        if self.tif_data is not None:
            self.current_frame = frame_index
            brightfield_channel = int(self.brightfield_channel.text())

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

            # Draw circles for the current frame's selections
            painter = QPainter(pixmap)
            pen = QPen(Qt.red, 2)  # Set the circle color and thickness
            painter.setPen(pen)

            if self.current_frame in self.selections:
                for x, y in self.selections[self.current_frame]:
                    # Scale the coordinates to match the magnified display
                    painter.drawEllipse(QPointF(x * self.image_scale, y * self.image_scale), self.radius * self.image_scale, self.radius * self.image_scale) 

            painter.end()

            # if self.current_frame in self.selections:
            #     for x, y in self.selections[self.current_frame]:
            #         self.draw_ellipse(pixmap, x * 2, y * 2, 40, 10, 45)

            # Display the updated pixmap
            self.image_label.setPixmap(pixmap)

    def draw_ellipse(self, pixmap, x, y, major, minor, angle):
        """
        Draw an ellipse on a given QPixmap.

        Parameters:
        pixmap (QPixmap): The pixmap on which to draw the ellipse.
        x (int): X-coordinate of the center of the ellipse.
        y (int): Y-coordinate of the center of the ellipse.
        major (int): Length of the major axis.
        minor (int): Length of the minor axis.
        angle (float): Rotation angle of the ellipse (in degrees).
        """

        # Create QPainter to draw on the pixmap
        painter = QPainter(pixmap)
        
        # Set pen properties (color, thickness)
        pen = QPen(QColor(255, 255, 0, 128), 2)  # Yellow color, thickness 2
        painter.setPen(pen)
        
        # Move painter to the center of the ellipse
        painter.translate(x, y)

        # Rotate painter by the given angle
        painter.rotate(angle)

        # Draw the ellipse using the major and minor axes
        painter.drawEllipse(QPointF(0, 0), major / 2, minor / 2)  # QPainter draws from the center

        # End the painter object to finalize drawing
        painter.end()
        
    def add_measurements(self):

        print(self.selections)

        for frame, points in self.selections.items():
            for x, y in points:
                print(frame, x, y)


        # # For now, we'll add dummy data to the spreadsheet
        # for i in range(10):  # Adding rows of dummy data
        #     self.table.setItem(i, 0, QTableWidgetItem(f"Measurement {i+1}"))
        #     self.table.setItem(i, 1, QTableWidgetItem(str(np.random.rand())))
        #     self.table.setItem(i, 2, QTableWidgetItem("um"))
        #     self.table.setItem(i, 3, QTableWidgetItem("Sample note"))

    def save_measurements(self):
        print("save")
        pass

    def copy_measurements(self):
        print("copy")
        pass

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = PyBudGUI()
    window.show()
    sys.exit(app.exec_())
