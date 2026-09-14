import numpy as np
import umap
from scipy.stats import entropy as scipy_entropy
from sklearn.metrics import davies_bouldin_score, silhouette_score

from app.services.clustering import KDEWatershedClusterer


def _kde_entropy(kde_values: np.ndarray, bins: int = 1000) -> float:
    hist, _ = np.histogram(kde_values.flatten(), bins=bins, density=True)
    return scipy_entropy(hist)


def grid_search(
    vectors: np.ndarray,
    n_neighbors_list: list[int],
    min_dist_list: list[float],
    probe_bw: float,
    probe_grid_size: int,
    probe_neighborhood: int,
) -> list[dict]:
    """UMAP n_neighbors/min_dist grid search อิงตาม UmapClustering._parallel_worker_func
    ใน old-concept-code/main.py — score = entropy(KDE) + silhouette - davies_bouldin

    คืน list เรียงจาก score สูงสุดก่อน แต่ละ entry มี xy/kde_dict/centers ครบ ใช้ทั้งเลือก
    best param และ debug/visualize ทีหลัง
    """
    param_list = [{"n_neighbors": n, "min_dist": d} for n in n_neighbors_list for d in min_dist_list]

    ranking = []
    for params in param_list:
        reducer = umap.UMAP(n_components=2, metric="cosine", random_state=42, **params)
        xy_probe = reducer.fit_transform(vectors)

        probe_clusterer = KDEWatershedClusterer(
            bw_method=probe_bw, grid_size=probe_grid_size, neighborhood_size=probe_neighborhood
        )
        probe_labels = probe_clusterer.fit_predict(xy_probe)

        # กัน -1 (noise) และ -2 (bridge) ไม่ให้ถูกนับเป็น "cluster จริง" ตอนให้คะแนน
        core_mask = probe_labels >= 0
        if core_mask.sum() > 1 and len(np.unique(probe_labels[core_mask])) > 1:
            sil = silhouette_score(xy_probe[core_mask], probe_labels[core_mask])
            db = davies_bouldin_score(xy_probe[core_mask], probe_labels[core_mask])
        else:
            sil, db = -1.0, float("inf")

        entp = _kde_entropy(probe_clusterer.kde_dict_["kde_values"])
        score = entp + sil - db

        ranking.append(
            {
                **params,
                "silhouette": sil,
                "davies_bouldin": db,
                "entropy": entp,
                "score": score,
                "xy": xy_probe,
                "kde_dict": probe_clusterer.kde_dict_,
                "centers": probe_clusterer.cluster_centers_,
            }
        )

    ranking.sort(key=lambda r: r["score"], reverse=True)
    return ranking
