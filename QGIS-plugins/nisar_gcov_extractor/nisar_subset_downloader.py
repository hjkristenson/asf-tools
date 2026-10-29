import os
import tempfile
from osgeo import gdal
from qgis.core import (
    QgsTask,
    QgsMessageLog,
    Qgis,
    QgsRasterLayer,
    QgsProject,
    QgsCoordinateTransform,
    QgsCoordinateReferenceSystem,
    QgsRectangle
)
from qgis.utils import iface


class NisarSubsetTask(QgsTask):
    def __init__(self, description, h5_https_url, bbox_target_crs, output_dir, bearer_token,
                 canvas_crs_authid="EPSG:4326"):
        super().__init__(description, QgsTask.CanCancel)
        self.h5_url = h5_https_url
        self.bbox = bbox_target_crs  # Expected as [xmin, ymin, xmax, ymax]
        self.out_dir = output_dir
        self.token = bearer_token
        self.canvas_crs = str(canvas_crs_authid)
        self.target_layers = ["HHHH", "HVHV", "VVVV", "VHVH", "mask"]
        self.extracted_files = []

    def _gdal_progress_callback(self, complete, message, cb_data):
        if self.isCanceled():
            return 0  # Abort C++ execution immediately
        self.setProgress(complete * 100)
        return 1

    def run(self):
        try:
            gdal.UseExceptions()

            cookie_file = os.path.join(tempfile.gettempdir(), "gdal_cookies.txt")

            h5_filename = os.path.basename(self.h5_url.split("?")[0])
            base_granule_name = os.path.splitext(h5_filename)[0]

            # ------------------------------------------------------------------
            # 1. GDAL VSI Configuration Flags
            # ------------------------------------------------------------------
            gdal.SetConfigOption("GDAL_HTTP_BEARER", self.token)
            gdal.SetConfigOption("GDAL_HTTP_AUTH", "BEARER")
            gdal.SetConfigOption("GDAL_HTTP_COOKIEFILE", cookie_file)
            gdal.SetConfigOption("GDAL_HTTP_COOKIEJAR", cookie_file)
            gdal.SetConfigOption("CPL_VSIL_CURL_USE_HEAD", "NO")
            gdal.SetConfigOption("GDAL_DISABLE_READDIR_ON_OPEN", "TRUE")
            gdal.SetConfigOption("HDF5_LIST_ALL_SUBDATASETS", "YES")

            # CLI Performance Flags
            gdal.SetConfigOption("CPL_VSIL_CURL_CHUNK_SIZE", "2097152")  # 2 MB Chunk
            gdal.SetConfigOption("CPL_VSIL_CURL_CACHE_SIZE", "1073741824")  # 1 GB VSI Cache
            gdal.SetConfigOption("GDAL_CACHEMAX", "64000000")  # 64 MB RAM Cache
            gdal.SetConfigOption("GDAL_HTTP_MERGE_CONSECUTIVE_RANGES", "YES")
            gdal.SetConfigOption("GDAL_HTTP_MULTIPLEX", "YES")
            gdal.SetConfigOption("GDAL_NUM_THREADS", "ALL_CPUS")

            vsi_url = f"/vsicurl/{self.h5_url}"
            QgsMessageLog.logMessage(f"Connecting via Fast VSI: {vsi_url}", "NISAR Extractor", Qgis.Info)

            # ------------------------------------------------------------------
            # 2. Strict Coordinate Transformation to WGS84 Longitude/Latitude
            # ------------------------------------------------------------------
            cutline_wkt = None
            cutline_srs = "WGS84"

            if self.bbox:
                xmin, ymin, xmax, ymax = self.bbox[0], self.bbox[1], self.bbox[2], self.bbox[3]

                # Check if coordinates are in projected meters (Web Mercator or UTM)
                is_meter_units = (abs(xmin) > 180.0 or abs(ymin) > 90.0 or abs(xmax) > 180.0 or abs(ymax) > 90.0)

                src_crs = QgsCoordinateReferenceSystem()
                if not src_crs.createFromUserInput(self.canvas_crs) or is_meter_units:
                    if is_meter_units and src_crs.isGeographic():
                        src_crs = QgsCoordinateReferenceSystem("EPSG:3857")

                dst_crs = QgsCoordinateReferenceSystem("OGC:CRS84")

                if is_meter_units or not src_crs.isGeographic():
                    try:
                        transform = QgsCoordinateTransform(src_crs, dst_crs, QgsProject.instance())
                        src_rect = QgsRectangle(xmin, ymin, xmax, ymax)
                        wgs84_rect = transform.transformBoundingBox(src_rect)

                        xmin, ymin = wgs84_rect.xMinimum(), wgs84_rect.yMinimum()
                        xmax, ymax = wgs84_rect.xMaximum(), wgs84_rect.yMaximum()
                        QgsMessageLog.logMessage(
                            f"Normalized BBOX from projected meters ({src_crs.authid()}) to WGS84: [{xmin:.6f}, {ymin:.6f}, {xmax:.6f}, {ymax:.6f}]",
                            "NISAR Extractor",
                            Qgis.Info
                        )
                    except Exception as te:
                        QgsMessageLog.logMessage(f"BBOX Reprojection Warning: {str(te)}", "NISAR Extractor",
                                                 Qgis.Warning)

                cutline_wkt = f"POLYGON(({xmin:.6f} {ymin:.6f}, {xmax:.6f} {ymin:.6f}, {xmax:.6f} {ymax:.6f}, {xmin:.6f} {ymax:.6f}, {xmin:.6f} {ymin:.6f}))"
                QgsMessageLog.logMessage(f"Applying Cutline WKT ({cutline_srs}): {cutline_wkt}", "NISAR Extractor",
                                         Qgis.Info)

            # ------------------------------------------------------------------
            # 3. Direct Subdataset Warping (Polarizations + Mask)
            # ------------------------------------------------------------------
            subdataset_template = f'HDF5:"{vsi_url}"://science/LSAR/GCOV/grids/frequencyA/{{layer}}'

            for layer in self.target_layers:
                if self.isCanceled():
                    return False

                sub_path = subdataset_template.format(layer=layer)
                out_filename = f"{base_granule_name}_{layer}.tif"
                out_path = os.path.join(self.out_dir, out_filename)

                QgsMessageLog.logMessage(f"CLI-Direct Warp: {layer} -> {out_filename}", "NISAR Extractor", Qgis.Info)

                warp_kwargs = {
                    "format": "GTiff",
                    "dstAlpha": True,
                    "multithread": True,
                    "callback": self._gdal_progress_callback,
                    "warpOptions": ["NUM_THREADS=ALL_CPUS"],
                    "creationOptions": [
                        "COMPRESS=DEFLATE",
                        "PREDICTOR=2",
                        "TILED=YES",
                        "BLOCKXSIZE=256",
                        "BLOCKYSIZE=256"
                    ]
                }

                if cutline_wkt:
                    warp_kwargs["cutlineWKT"] = cutline_wkt
                    warp_kwargs["cutlineSRS"] = cutline_srs
                    warp_kwargs["cropToCutline"] = True

                warp_opts = gdal.WarpOptions(**warp_kwargs)

                try:
                    res_ds = gdal.Warp(out_path, sub_path, options=warp_opts)
                    res_ds = None  # Flush raster write to disk

                    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
                        self.extracted_files.append(out_path)
                        QgsMessageLog.logMessage(f"Successfully generated: {out_filename}", "NISAR Extractor",
                                                 Qgis.Info)
                except Exception as we:
                    QgsMessageLog.logMessage(f"Warp notice for {layer}: {str(we)}", "NISAR Extractor", Qgis.Info)

            QgsMessageLog.logMessage(f"NISAR extraction complete! Extracted {len(self.extracted_files)} files.",
                                     "NISAR Extractor", Qgis.Info)
            return True

        except Exception as e:
            QgsMessageLog.logMessage(f"Extraction failed: {str(e)}", "NISAR Extractor", Qgis.Critical)
            return False

    def finished(self, result):
        if result and self.extracted_files:
            loaded_count = 0
            for file_path in self.extracted_files:
                layer_name = os.path.basename(file_path)
                raster_layer = QgsRasterLayer(file_path, layer_name, "gdal")

                if raster_layer.isValid():
                    QgsProject.instance().addMapLayer(raster_layer)
                    loaded_count += 1

            if iface:
                iface.messageBar().pushMessage(
                    "NISAR Extractor",
                    f"Extraction complete! Loaded {loaded_count} layer(s) to map canvas.",
                    level=Qgis.Success,
                    duration=5
                )
        elif iface:
            iface.messageBar().pushMessage(
                "NISAR Extractor",
                "Extraction failed or returned no files.",
                level=Qgis.Warning,
                duration=5
            )
