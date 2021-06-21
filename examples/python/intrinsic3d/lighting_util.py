import open3d as o3d
import numpy as np


def color_to_intensity(rgb):
    return 0.2126 * rgb[:, 0] + 0.7152 * rgb[:, 1] + 0.0722 * rgb[:, 2]


def backward_sh(ns, intensities, albedos):
    nx = ns[:, 0]
    ny = ns[:, 1]
    nz = ns[:, 2]

    # n x 9
    A = np.zeros((len(nx), 9))
    A[:, 0] = 1
    A[:, 1] = ny
    A[:, 2] = nz
    A[:, 3] = nx
    A[:, 4] = (nx * ny)
    A[:, 5] = (ny * nz)
    A[:, 6] = (2 * nz**2 - nx**2 - ny**2)
    A[:, 7] = (nx * nz)
    A[:, 8] = (nx**2 - ny**2)

    # n x 1
    b = intensities / albedos
    l = np.linalg.solve(A.T @ A, A.T @ b)

    return l


def forward_sh(l, ns):
    '''
    SH coeffs: l: (9, 1)
    normals: ns: (N, 3)
    '''
    nx = ns[:, 0]
    ny = ns[:, 1]
    nz = ns[:, 2]

    return l[0] \
        + l[1] * ny \
        + l[2] * nz \
        + l[3] * nx \
        + l[4] * (nx * ny) \
        + l[5] * (ny * nz) \
        + l[6] * (2 * nz**2 - nx**2 - ny**2) \
        + l[7] * (nx * nz) \
        + l[8] * (nx**2 - ny**2)