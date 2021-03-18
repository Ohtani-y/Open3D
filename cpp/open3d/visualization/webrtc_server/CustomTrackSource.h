// ----------------------------------------------------------------------------
// -                        Open3D: www.open3d.org                            -
// ----------------------------------------------------------------------------
// The MIT License (MIT)
//
// Copyright (c) 2021 www.open3d.org
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

#pragma once

#include <absl/types/optional.h>
#include <api/media_stream_interface.h>
#include <api/notifier.h>
#include <api/sequence_checker.h>
#include <api/video/recordable_encoded_frame.h>
#include <api/video/video_frame.h>
#include <api/video/video_sink_interface.h>
#include <api/video/video_source_interface.h>
#include <media/base/media_channel.h>

namespace open3d {
namespace visualization {
namespace webrtc_server {

class CustomTrackSourceInterface : public webrtc::VideoTrackSourceInterface {};

// VideoTrackSource is a convenience base class for implementations of
// VideoTrackSourceInterface.
class VideoTrackSource : public webrtc::Notifier<CustomTrackSourceInterface> {
public:
    explicit VideoTrackSource(bool remote);
    void SetState(webrtc::MediaSourceInterface::SourceState new_state);

    webrtc::MediaSourceInterface::SourceState state() const override {
        return state_;
    }
    bool remote() const override { return remote_; }

    bool is_screencast() const override { return false; }
    absl::optional<bool> needs_denoising() const override {
        return absl::nullopt;
    }

    bool GetStats(Stats* stats) override { return false; }

    void AddOrUpdateSink(rtc::VideoSinkInterface<webrtc::VideoFrame>* sink,
                         const rtc::VideoSinkWants& wants) override;
    void RemoveSink(rtc::VideoSinkInterface<webrtc::VideoFrame>* sink) override;

    bool SupportsEncodedOutput() const override { return false; }
    void GenerateKeyFrame() override {}
    void AddEncodedSink(rtc::VideoSinkInterface<webrtc::RecordableEncodedFrame>*
                                sink) override {}
    void RemoveEncodedSink(
            rtc::VideoSinkInterface<webrtc::RecordableEncodedFrame>* sink)
            override {}

protected:
    virtual rtc::VideoSourceInterface<webrtc::VideoFrame>* source() = 0;

private:
    webrtc::SequenceChecker worker_thread_checker_;
    webrtc::MediaSourceInterface::SourceState state_;
    const bool remote_;
};

}  // namespace webrtc_server
}  // namespace visualization
}  // namespace open3d
