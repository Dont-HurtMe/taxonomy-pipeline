import numpy as np
from scipy.ndimage import maximum_filter
from scipy.stats import gaussian_kde
from skimage.segmentation import watershed


class KDEWatershedClusterer:
    """KDE density + watershed segmentation clusterer, with boundary/bridge point detection.

    Port ตรงจาก lab/clustering_model/clustering_model_lab.ipynb — อ้างอิง
    old-concept-code/clustering.py + docs/hierarchical-taxonomy-concept.md (section 11)
    """

    def __init__(
        self,
        bw_method: float = 0.1,
        grid_size: int = 100,
        neighborhood_size: int = 5,
        rel_threshold: float | None = None,
        bridge_window: int = 3,
        bridge_rel_threshold: float | None = None,
    ):
        self.bw_method = bw_method
        self.grid_size = grid_size
        self.neighborhood_size = neighborhood_size
        self.rel_threshold = rel_threshold if rel_threshold is not None else self.bw_method
        self.bridge_window = bridge_window
        self.bridge_rel_threshold = bridge_rel_threshold
        self.embedding_, self.kde_dict_, self.peaks_, self.cluster_centers_, self.labels_ = [None] * 5
        self.bridge_between_: dict[int, list[int]] = {}

    def fit_predict(self, X: np.ndarray) -> np.ndarray:
        self.embedding_ = X
        x, y = X[:, 0], X[:, 1]
        self.kde_dict_ = self._calculate_kde(x, y)
        self.peaks_ = self._find_peaks()
        if self.peaks_:
            self.cluster_centers_ = np.array([[p["x"], p["y"]] for p in self.peaks_])
        else:
            self.cluster_centers_ = np.empty((0, 2))
        self.labels_ = self._assign_labels_by_watershed(X)
        return self.labels_

    def get_results_dict(self) -> dict:
        if self.labels_ is None:
            raise RuntimeError("ต้องรัน .fit_predict(X) ก่อน")
        centers_dict = {str(i): c.tolist() for i, c in enumerate(self.cluster_centers_)}
        serializable_kde = {k: v.tolist() if isinstance(v, np.ndarray) else v for k, v in self.kde_dict_.items()}
        return {
            "labels": self.labels_.tolist(),
            "centers": centers_dict,
            "kde_dict": serializable_kde,
            "xy": self.embedding_.tolist(),
            "bridge_between": {str(k): v for k, v in self.bridge_between_.items()},
        }

    def _calculate_kde(self, x: np.ndarray, y: np.ndarray) -> dict:
        kde = gaussian_kde(np.vstack([x, y]), bw_method=self.bw_method)
        xmin, xmax, ymin, ymax = x.min() - 1, x.max() + 1, y.min() - 1, y.max() + 1
        x_grid, y_grid = np.meshgrid(np.linspace(xmin, xmax, self.grid_size), np.linspace(ymin, ymax, self.grid_size))
        kde_values = kde(np.vstack([x_grid.ravel(), y_grid.ravel()])).reshape(x_grid.shape)
        return {"x_grid": x_grid, "y_grid": y_grid, "kde_values": kde_values, "bw_method": self.bw_method}

    def _find_peaks(self) -> list[dict]:
        vals = self.kde_dict_["kde_values"]
        mask = (vals == maximum_filter(vals, size=self.neighborhood_size)) & (vals > vals.max() * self.rel_threshold)
        rows, cols = np.where(mask)
        if len(rows) == 0:
            return []
        return [{"x": self.kde_dict_["x_grid"][r, c], "y": self.kde_dict_["y_grid"][r, c]} for r, c in zip(rows, cols)]

    def _assign_labels_by_watershed(self, xy: np.ndarray) -> np.ndarray:
        self.bridge_between_ = {}
        if not self.peaks_:
            return np.full(xy.shape[0], -1)

        kde_values = self.kde_dict_["kde_values"]
        xmin, xmax = self.kde_dict_["x_grid"][0, 0], self.kde_dict_["x_grid"][0, -1]
        ymin, ymax = self.kde_dict_["y_grid"][0, 0], self.kde_dict_["y_grid"][-1, 0]

        markers_grid = np.zeros_like(kde_values, dtype=int)
        for i, peak in enumerate(self.peaks_):
            r = np.abs(self.kde_dict_["y_grid"][:, 0] - peak["y"]).argmin()
            c = np.abs(self.kde_dict_["x_grid"][0, :] - peak["x"]).argmin()
            markers_grid[r, c] = i + 1

        # watershed_line=True: สันเขา (ridge) ระหว่าง basin ได้ label 0 แยกออกมา
        # แทนที่จะยัดทุก grid cell เข้า basin ใดบาสินหนึ่งเสมอ (ดู docs section 11)
        labels_grid = watershed(-kde_values, markers_grid, mask=np.ones_like(kde_values, dtype=bool), watershed_line=True)

        cols = np.clip(((xy[:, 0] - xmin) / (xmax - xmin) * (self.grid_size - 1)).astype(int), 0, self.grid_size - 1)
        rows = np.clip(((xy[:, 1] - ymin) / (ymax - ymin) * (self.grid_size - 1)).astype(int), 0, self.grid_size - 1)

        half_w = self.bridge_window // 2
        labels = np.full(xy.shape[0], -1)

        for idx, (r, c) in enumerate(zip(rows, cols)):
            r0, r1 = max(0, r - half_w), min(self.grid_size, r + half_w + 1)
            c0, c1 = max(0, c - half_w), min(self.grid_size, c + half_w + 1)
            window = labels_grid[r0:r1, c0:c1]
            neighbor_ids = sorted(int(v) for v in np.unique(window) if v > 0)

            if len(neighbor_ids) == 0:
                labels[idx] = -1
            elif len(neighbor_ids) == 1:
                labels[idx] = neighbor_ids[0] - 1
            else:
                cluster_ids = [n - 1 for n in neighbor_ids]
                peak_densities = {}
                for cid in cluster_ids:
                    peak = self.peaks_[cid]
                    rr = np.abs(self.kde_dict_["y_grid"][:, 0] - peak["y"]).argmin()
                    cc = np.abs(self.kde_dict_["x_grid"][0, :] - peak["x"]).argmin()
                    peak_densities[cid] = kde_values[rr, cc]

                if self.bridge_rel_threshold is not None:
                    point_density = kde_values[r, c]
                    best_cid = max(peak_densities, key=peak_densities.get)
                    if point_density >= self.bridge_rel_threshold * peak_densities[best_cid]:
                        labels[idx] = best_cid
                        continue

                labels[idx] = -2
                self.bridge_between_[idx] = cluster_ids

        return labels
