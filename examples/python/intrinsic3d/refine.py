import open3d as o3d
import numpy as np
import argparse
import torch
import torch.nn

from tsdf_util import *
from lighting_util import *
from voxel_util import *
from rgbd_util import *


def to_torch(np_dict):
    torch_dict = {}
    for key in np_dict:
        torch_dict[key] = torch.from_numpy(np_dict[key]).cuda()

    return torch_dict


def compute_surface_and_normal(voxel_coords, voxel_tsdf, key, selection,
                               voxel_nbs):
    index_data = selection[key]
    nx = voxel_tsdf[voxel_nbs['index_xp'][index_data]] - voxel_tsdf[
        voxel_nbs['index_xm'][index_data]]
    ny = voxel_tsdf[voxel_nbs['index_yp'][index_data]] - voxel_tsdf[
        voxel_nbs['index_ym'][index_data]]
    nz = voxel_tsdf[voxel_nbs['index_zp'][index_data]] - voxel_tsdf[
        voxel_nbs['index_zm'][index_data]]
    norm = (nx**2 + ny**2 + nz**2).sqrt()

    normals = torch.stack((nx, ny, nz)).T / norm.unsqueeze(-1)
    surfaces = voxel_coords[index_data] - voxel_tsdf[index_data].unsqueeze(
        -1) * normals * sdf_trunc

    return surfaces, normals


def project(xyz, color, depth, pose):
    # NOTE: non autodiff w.r.t. pose for now, only find association
    T = np.linalg.inv(pose)
    R = T[:3, :3]
    t = T[:3, 3:]

    projection = K_color @ (R @ xyz.T + t)

    u = (projection[0] / projection[2]).round().astype(int)
    v = (projection[1] / projection[2]).round().astype(int)

    color_np = np.asarray(color)
    depth_np = np.asarray(depth).astype(np.float32) / 1000.0
    h, w, _ = color_np.shape

    # mask at point's shape
    mask = (u >= 0) & (u < w) & (v >= 0) & (v < h)

    corres_depth = np.zeros_like(mask, dtype=np.float64)
    corres_depth[mask] = depth_np[v[mask], u[mask]]

    mask[corres_depth == 0] = False

    intensity = np.zeros((len(xyz)), dtype=np.float64)
    intensity[mask] = color_to_intensity(color_np[v[mask], u[mask]]) / 255.0

    return mask, intensity


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('path_dataset')

    # Selections
    parser.add_argument('--spatial', default='voxels_spatial.npz')
    parser.add_argument('--selection', default='tsdf_selection.npz')
    parser.add_argument('--association', default='tsdf_association.npz')

    parser.add_argument('--input', default='colored_voxels_fine.npz')
    parser.add_argument('--output', default='colored_voxels_refined.npz')

    args = parser.parse_args()

    # Load data
    spatial = np.load(args.spatial)
    selection = to_torch(dict(np.load(args.selection)))
    input_data = np.load(args.input)
    association = to_torch(np.load(args.association))

    voxel_nbs = to_torch(get_nb_dict(spatial))
    voxel_coords = torch.from_numpy(spatial['voxel_coords']).cuda()

    voxel_tsdf = torch.from_numpy(input_data['voxel_tsdf']).cuda()
    voxel_color = torch.from_numpy(input_data['voxel_color']).cuda()
    voxel_intensity = color_to_intensity(voxel_color)
    voxel_chromaticity = voxel_color / voxel_intensity.unsqueeze(dim=-1)

    # Uniformly initialized to 0.6
    voxel_albedo = torch.ones_like(voxel_intensity) * 0.6

    # TODO: if it eats too much memory,
    # map index_data_xp to index_data_c in another hashmap in preprocessing
    index_data = selection['index_data_c']
    index_data_xp = selection['index_data_xp']
    index_data_yp = selection['index_data_yp']
    index_data_zp = selection['index_data_zp']

    # Estimate SH
    surfaces, normals = compute_surface_and_normal(voxel_coords, voxel_tsdf,
                                                   'index_data_c', selection,
                                                   voxel_nbs)
    l = backward_sh(normals.cpu().numpy(),
                    voxel_intensity[index_data].cpu().numpy(),
                    voxel_albedo[index_data].cpu().numpy())
    l = torch.from_numpy(l).cuda()

    print('Loading keyframes ...')
    colors, depths, poses = load_keyframes(args.path_dataset, check=False)
    print('Loading finished.')
    assoc = association['association_mask']
    assoc_weight = association['association_weight']
    n_kf = len(poses)

    # Now start to optimize
    # voxel_tsdf is reserved for stability check
    param_tsdf = torch.nn.Parameter(voxel_tsdf.clone())
    param_albedo = torch.nn.Parameter(voxel_albedo)
    optimizer = torch.optim.Adam([param_tsdf, param_albedo], lr=1e-3)

    max_epochs = 50

    lambda_data = 1000
    lambda_tsdf_laplacian = 0.01
    lambda_tsdf_stability = 0.1
    lambda_albedo = 0.1
    for epoch in range(max_epochs):
        surfaces_c, normals_c = compute_surface_and_normal(
            voxel_coords, param_tsdf, 'index_data_c', selection, voxel_nbs)
        surfaces_xp, normals_xp = compute_surface_and_normal(
            voxel_coords, param_tsdf, 'index_data_xp', selection, voxel_nbs)
        surfaces_yp, normals_yp = compute_surface_and_normal(
            voxel_coords, param_tsdf, 'index_data_yp', selection, voxel_nbs)
        surfaces_zp, normals_zp = compute_surface_and_normal(
            voxel_coords, param_tsdf, 'index_data_zp', selection, voxel_nbs)

        # if epoch % 10 == 0:
        #     pcd_c = make_o3d_pcd(
        #         surfaces_c.detach().cpu().numpy(),
        #         normals=normals_c.detach().cpu().numpy(),
        #         colors=param_albedo[
        #             selection['index_data_c']].detach().cpu().numpy())
        #     o3d.visualization.draw([pcd_c])
        # pcd_xp = make_o3d_pcd(surfaces_xp.detach().cpu().numpy(),
        #                       normals=normals_xp.detach().cpu().numpy())
        # pcd_yp = make_o3d_pcd(surfaces_yp.detach().cpu().numpy(),
        #                       normals=normals_yp.detach().cpu().numpy())
        # pcd_zp = make_o3d_pcd(surfaces_zp.detach().cpu().numpy(),
        #                       normals=normals_zp.detach().cpu().numpy())
        # o3d.visualization.draw([pcd_c, pcd_xp, pcd_yp, pcd_zp])

        loss_data = 0
        for i in range(n_kf):
            sel = assoc[i]
            w = assoc_weight[i, sel]

            surfaces_c_sel = surfaces_c[sel]
            normals_c_sel = normals_c[sel]
            albedo_c_sel = param_albedo[index_data][sel]
            mask_c_sel, intensity_c_sel = project(
                surfaces_c_sel.detach().cpu().numpy(), colors[i], depths[i],
                poses[i])

            surfaces_xp_sel = surfaces_xp[sel]
            normals_xp_sel = normals_xp[sel]
            albedo_xp_sel = param_albedo[index_data_xp][sel]
            mask_xp_sel, intensity_xp_sel = project(
                surfaces_xp_sel.detach().cpu().numpy(), colors[i], depths[i],
                poses[i])

            surfaces_yp_sel = surfaces_yp[sel]
            normals_yp_sel = normals_yp[sel]
            albedo_yp_sel = param_albedo[index_data_yp][sel]
            mask_yp_sel, intensity_yp_sel = project(
                surfaces_yp_sel.detach().cpu().numpy(), colors[i], depths[i],
                poses[i])

            surfaces_zp_sel = surfaces_zp[sel]
            normals_zp_sel = normals_zp[sel]
            albedo_zp_sel = param_albedo[index_data_zp][sel]
            mask_zp_sel, intensity_zp_sel = project(
                surfaces_zp_sel.detach().cpu().numpy(), colors[i], depths[i],
                poses[i])

            mask = mask_c_sel & mask_xp_sel & mask_yp_sel & mask_zp_sel
            dIx = torch.from_numpy(
                (intensity_xp_sel - intensity_c_sel)[mask]).cuda()
            dIy = torch.from_numpy(
                (intensity_yp_sel - intensity_c_sel)[mask]).cuda()
            dIz = torch.from_numpy(
                (intensity_zp_sel - intensity_c_sel)[mask]).cuda()

            # Next compute dBx, dBy, dBz
            mask = torch.from_numpy(mask).cuda()
            b_c = forward_sh(l, normals_c_sel) * albedo_c_sel
            b_xp = forward_sh(l, normals_xp_sel) * albedo_xp_sel
            b_yp = forward_sh(l, normals_yp_sel) * albedo_yp_sel
            b_zp = forward_sh(l, normals_zp_sel) * albedo_zp_sel

            dBx = (b_xp - b_c)[mask]
            dBy = (b_yp - b_c)[mask]
            dBz = (b_zp - b_c)[mask]

            loss_data_i = (dBx - dIx)**2 + (dBy - dIy)**2 + (dBz - dIz)**2
            loss_data = loss_data + (w[mask] * loss_data_i).sum()

        # Regularizer: TSDF Stability
        loss_tsdf_stability = ((param_tsdf - voxel_tsdf)**2).sum()

        # Regularizer: TSDF Laplacian
        tsdf_c = param_tsdf[selection['index_lap_c']]
        tsdf_xp = param_tsdf[selection['index_lap_xp']]
        tsdf_yp = param_tsdf[selection['index_lap_yp']]
        tsdf_zp = param_tsdf[selection['index_lap_zp']]
        tsdf_xm = param_tsdf[selection['index_lap_xm']]
        tsdf_ym = param_tsdf[selection['index_lap_ym']]
        tsdf_zm = param_tsdf[selection['index_lap_zm']]

        dxx = tsdf_xp + tsdf_xm - 2 * tsdf_c
        dyy = tsdf_yp + tsdf_ym - 2 * tsdf_c
        dzz = tsdf_zp + tsdf_zm - 2 * tsdf_c

        loss_tsdf_laplacian = ((dxx + dyy + dzz)**2).sum()

        # Regularizer: albedo
        loss_albedo_chromaticity = 0
        rho = lambda x: 1 / (1 + x)**3

        for key in ['xp', 'yp', 'zp', 'xm', 'ym', 'zm']:
            index_c = selection['index_' + key + '_self']
            index_nb = selection['index_' + key + '_nb']
            w = (voxel_chromaticity[index_c] -
                 voxel_chromaticity[index_nb]).norm(dim=1)
            albedo_diff = (param_albedo[index_c] - param_albedo[index_nb])**2
            loss_albedo_chromaticity += (rho(w) * albedo_diff).sum()

        loss = lambda_data * loss_data \
             + lambda_tsdf_stability * loss_tsdf_stability \
             + lambda_tsdf_laplacian * loss_tsdf_laplacian \
             + lambda_albedo * loss_albedo_chromaticity
        print(
            'epoch {}, loss = {:.2f}, data: {:.2f} stability reg: {:.2f}, laplacian reg: {:.2f}, albedo reg: {:.2f}'
            .format(epoch, loss.item(), lambda_data * loss_data.item(),
                    lambda_tsdf_stability * loss_tsdf_stability.item(),
                    lambda_tsdf_laplacian * loss_tsdf_laplacian.item(),
                    lambda_albedo * loss_albedo_chromaticity.item()))

        loss.backward()
        optimizer.step()

    np.savez(args.output,
             voxel_tsdf=param_tsdf.detach().cpu().numpy(),
             voxel_albedo=param_albedo.detach().cpu().numpy(),
             voxel_color=voxel_color.cpu().numpy())