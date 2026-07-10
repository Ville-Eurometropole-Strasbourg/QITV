"""
map_tool.py
A minimal QgsMapTool that emits one feature-picked signal then deactivates.
Used by TubeDialog to fill the AAA/AAB/AAF fields from a map click.
"""

from qgis.core import QgsGeometry
from qgis.gui import QgsMapTool
from qgis.PyQt.QtCore import Qt, pyqtSignal
from qgis.PyQt.QtGui import QCursor


class FeaturePickerTool(QgsMapTool):
    """
    Single-use map tool.

    After the user clicks on the canvas the tool:
      1. Finds the closest feature in `layer`.
      2. Emits feature_picked(feature).
      3. Restores the previous map tool automatically.
    """

    feature_picked = pyqtSignal(object)

    def __init__(self, canvas, layer):
        super().__init__(canvas)
        self._layer = layer
        self._previous_tool = canvas.mapTool()
        self.setCursor(QCursor(Qt.CrossCursor))

    def canvasReleaseEvent(self, event):  # noqa: N802
        """Triggered on mouse release — find the nearest feature and emit."""
        point = self.toLayerCoordinates(self._layer, event.pos())

        radius = self.canvas().extent().width() * 5 / self.canvas().width()
        request_rect = QgsGeometry.fromPointXY(point).buffer(radius, 5).boundingBox()

        best_feature = None
        best_dist = float("inf")

        point_geom = QgsGeometry.fromPointXY(point)

        for feat in self._layer.getFeatures(request_rect):
            geom = feat.geometry()
            if geom is None:
                continue

            dist = geom.distance(point_geom)

            if dist < best_dist:
                best_dist = dist
                best_feature = feat

        self.feature_picked.emit(best_feature)
        self.canvas().setMapTool(self._previous_tool)

    def keyPressEvent(self, event):
        """Allow Escape to cancel without emitting."""
        if event.key() == Qt.Key_Escape:
            self.canvas().setMapTool(self._previous_tool)