// ----------------------------------------------------------------------------
// -                        Open3D: www.open3d.org                            -
// ----------------------------------------------------------------------------
// The MIT License (MIT)
//
// Copyright (c) 2018 www.open3d.org
//
// Permission is hereby granted, free of charge, to any person obtaining a copy
// of this software and associated documentation files (the "Software"), to deal
// in the Software without restriction, including without limitation the rights
// to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
// copies of the Software, and to permit persons to whom the Software is
// furnished to do so, subject to the following conditions:
//
// The above copyright notice and this permission notice shall be included in
// all copies or substantial portions of the Software.
//
// THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
// IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
// FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
// AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
// LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
// FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
// IN THE SOFTWARE.
// ----------------------------------------------------------------------------

#include "open3d/t/pipelines/registration/TransformationEstimation.h"

#include "open3d/t/pipelines/kernel/ComputeTransform.h"
#include "open3d/t/pipelines/kernel/TransformationConverter.h"

namespace open3d {
namespace t {
namespace pipelines {
namespace registration {

double TransformationEstimationPointToPoint::ComputeRMSE(
        const geometry::PointCloud &source,
        const geometry::PointCloud &target,
        const core::Tensor &correspondences) const {
    core::Device device = source.GetDevice();

    target.GetPoints().AssertDtype(source.GetPoints().GetDtype());
    if (target.GetDevice() != device) {
        utility::LogError(
                "Target Pointcloud device {} != Source Pointcloud's device {}.",
                target.GetDevice().ToString(), device.ToString());
    }

    // TODO: Optimise using kernel.
    core::Tensor valid = correspondences.Ne(-1).Reshape({-1});
    core::Tensor neighbour_indices =
            correspondences.IndexGet({valid}).Reshape({-1});
    core::Tensor source_points_indexed = source.GetPoints().IndexGet({valid});
    core::Tensor target_points_indexed =
            target.GetPoints().IndexGet({neighbour_indices});

    core::Tensor error_t = (source_points_indexed - target_points_indexed);
    error_t.Mul_(error_t);
    double error = error_t.Sum({0, 1}).To(core::Dtype::Float64).Item<double>();
    return std::sqrt(error /
                     static_cast<double>(neighbour_indices.GetLength()));
}

core::Tensor TransformationEstimationPointToPoint::ComputeTransformation(
        const geometry::PointCloud &source,
        const geometry::PointCloud &target,
        const core::Tensor &correspondences,
        int &inlier_cout) const {
    core::Device device = source.GetDevice();

    if (target.GetDevice() != device) {
        utility::LogError(
                "Target Pointcloud device {} != Source Pointcloud's device {}.",
                target.GetDevice().ToString(), device.ToString());
    }

    core::Tensor R, t;
    std::tie(R, t) = pipelines::kernel::ComputeRtPointToPoint(
            source.GetPoints(), target.GetPoints(), correspondences,
            inlier_cout);

    return t::pipelines::kernel::RtToTransformation(R, t);
}

double TransformationEstimationPointToPlane::ComputeRMSE(
        const geometry::PointCloud &source,
        const geometry::PointCloud &target,
        const core::Tensor &correspondences) const {
    core::Device device = source.GetDevice();

    target.GetPoints().AssertDtype(source.GetPoints().GetDtype());
    if (target.GetDevice() != device) {
        utility::LogError(
                "Target Pointcloud device {} != Source Pointcloud's device {}.",
                target.GetDevice().ToString(), device.ToString());
    }

    if (!target.HasPointNormals()) return 0.0;
    // TODO: Optimise using kernel.
    core::Tensor valid = correspondences.Ne(-1).Reshape({-1});
    core::Tensor neighbour_indices =
            correspondences.IndexGet({valid}).Reshape({-1});
    core::Tensor source_points_indexed = source.GetPoints().IndexGet({valid});
    core::Tensor target_points_indexed =
            target.GetPoints().IndexGet({neighbour_indices});
    core::Tensor target_normals_indexed =
            target.GetPointNormals().IndexGet({neighbour_indices});

    core::Tensor error_t = (source_points_indexed - target_points_indexed)
                                   .Mul_(target_normals_indexed);
    error_t.Mul_(error_t);
    double error = error_t.Sum({0, 1}).To(core::Dtype::Float64).Item<double>();
    return std::sqrt(error /
                     static_cast<double>(neighbour_indices.GetLength()));
}

core::Tensor TransformationEstimationPointToPlane::ComputeTransformation(
        const geometry::PointCloud &source,
        const geometry::PointCloud &target,
        const core::Tensor &correspondences,
        int &inlier_cout) const {
    core::Device device = source.GetDevice();

    if (target.GetDevice() != device) {
        utility::LogError(
                "Target Pointcloud device {} != Source Pointcloud's device {}.",
                target.GetDevice().ToString(), device.ToString());
    }

    // Get pose {6} of type Float64 from correspondences indexed source and
    // target point cloud.
    core::Tensor pose = pipelines::kernel::ComputePosePointToPlane(
            source.GetPoints(), target.GetPoints(), target.GetPointNormals(),
            correspondences, inlier_cout, this->kernel_);

    // Get transformation {4,4} of type Float64 from pose {6}.
    return pipelines::kernel::PoseToTransformation(pose);
}

double TransformationEstimationColoredICP::ComputeRMSE(
        const geometry::PointCloud &source,
        const geometry::PointCloud &target,
        const core::Tensor &correspondences) const {
    return 0.0;
}

core::Tensor TransformationEstimationColoredICP::ComputeTransformation(
        const geometry::PointCloud &source,
        const geometry::PointCloud &target,
        const core::Tensor &correspondences,
        int &inlier_cout) const {
    core::Device device = source.GetDevice();

    if (target.GetDevice() != device) {
        utility::LogError(
                "Target Pointcloud's device {} != Source Pointcloud's device "
                "{}.",
                target.GetDevice().ToString(), device.ToString());
    }

    auto target_clone = target.Clone();
//     core::Tensor color_gradients =
//             core::Tensor::Load("target_color_gradient_f32.npy");
//     target_clone.SetPointAttr(
//             "color_gradients",
//             color_gradients.To(device, target.GetPoints().GetDtype()));

    // Get pose {6} of type Float64 from correspondences indexed source and
    // target point cloud.
    core::Tensor pose = pipelines::kernel::ComputePoseColoredICP(
            source.GetPoints(), source.GetPointColors(), target_clone.GetPoints(),
            target_clone.GetPointNormals(), target_clone.GetPointColors(),
            target_clone.GetPointAttr("color_gradients"), correspondences,
            inlier_cout, this->kernel_, this->lambda_geometric_);

    // Get transformation {4,4} of type Float64 from pose {6}.
    core::Tensor transform = pipelines::kernel::PoseToTransformation(pose);
        std::cout << " Output: \n " << transform.ToString() << std::endl;
    /*
    Legacy:
         0.999993   0.00372512  0.000284199  -0.00639423
      -0.0037256     0.999992   0.00170515   0.00485329
    -0.000277845   -0.0017062     0.999999    0.0032935
               0            0            0            1

    CUDA:
        [[0.0391050 0.997924 -0.0511781 -13.0404],
        [0.0632854 -0.0535878 -0.996556 19.4114],
        [-0.997229 0.0357315 -0.0652495 -9.56064],
        [0.0 0.0 0.0 1.0]]


    CPU:
        [[0.0393034 0.997949 -0.0505279 -13.0397],
        [0.0636685 -0.0529653 -0.996565 19.4103],
        [-0.997197 0.0359513 -0.0656196 -9.5593],
        [0.0 0.0 0.0 1.0]]

    */

    return transform;
}

}  // namespace registration
}  // namespace pipelines
}  // namespace t
}  // namespace open3d
